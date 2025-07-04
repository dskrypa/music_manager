"""
Plex playlist management utilities

:author: Doug Skrypa
"""

from __future__ import annotations

import logging
from functools import cached_property
from typing import TYPE_CHECKING, Any, Collection
from xml.etree.ElementTree import Element, indent as _indent, tostring

from plexapi.audio import Track
from plexapi.exceptions import BadRequest
from plexapi.playlist import Playlist
from plexapi.utils import joinArgs

from ds_tools.output.color import colored
from ds_tools.output.formatting import bullet_list, format_duration
from ds_tools.output.prefix import LoggingPrefix

from ..config import config
from ..exceptions import InvalidPlaylist
from ..query import QueryResults
from .utils import PlaylistXmlDict, get_plex

if TYPE_CHECKING:
    from music.typing import PathLike
    from ..server import LocalPlexServer
    from ..typing import PlaylistType, AnsiColor

    OptServer = LocalPlexServer | None

__all__ = ['PlexPlaylist', 'compare_playlists']
log = logging.getLogger(__name__)

Tracks = Collection[Track] | QueryResults


class PlexPlaylist:
    plex: LocalPlexServer
    name: str
    lp: LoggingPrefix
    _externally_synced: bool | None = None
    _playlist: Playlist | None

    def __init__(
        self, name: str, plex: OptServer = None, playlist: Playlist | None = None, externally_synced: bool | None = None
    ):
        self.plex = get_plex(plex)
        self.name = name
        self._playlist = playlist
        self.externally_synced = externally_synced
        self.lp = LoggingPrefix(self.plex.dry_run)

    # region Create Playlist

    @classmethod
    def new(
        cls,
        name: str,
        plex: OptServer = None,
        content: Tracks = None,
        *,
        externally_synced: bool | None = None,
        **criteria,
    ) -> PlexPlaylist:
        self = cls(name, plex, externally_synced=externally_synced)
        self.create(content, **criteria)
        return self

    def create(self, content: Tracks = None, **criteria):
        # TODO: Add way to "restore" an ordered playlist where the original files have been replaced by higher
        #  quality versions
        items = list(_get_tracks(self.plex, content, **criteria))
        log.info(f'{self.lp.create} {self} with {len(items):,d} tracks', extra={'color': 10})
        log.debug(f'Creating {self} with tracks: {items}')
        if not self.plex.dry_run:
            self._playlist = Playlist.create(self.plex.server, self.name, items)

    # endregion

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}({self.name!r})'

    def __len__(self) -> int:
        return len(self.playlist)

    # region Properties

    @property
    def playlist(self) -> Playlist | None:
        if self._playlist is not None:
            return self._playlist

        playlists = self.plex.server.playlists()
        if (playlist := next((p for p in playlists if p.title == self.name), None)) is not None:
            self._playlist = playlist
        else:
            lc_name = self.name.lower()
            if (playlist := next((p for p in playlists if p.title.lower() == lc_name), None)) is not None:
                self._playlist = playlist
                self.name = playlist.title
        return self._playlist

    @property
    def exists(self) -> bool:
        return self.playlist is not None

    @cached_property
    def type(self) -> PlaylistType:
        """The type of content in this playlist (audio, video, or photo)"""
        try:
            return self.playlist.playlistType
        except AttributeError as e:
            raise InvalidPlaylist(f'{self} has no type because it does not exist') from e

    @cached_property
    def item_type(self) -> str:
        if self.type == 'audio':
            return 'track'
        else:
            raise AttributeError(f'item_type is not currently supported for playlist type={self.type!r}')

    @cached_property
    def is_smart(self) -> bool:
        try:
            return self.playlist.smart
        except AttributeError as e:
            raise InvalidPlaylist(f'{self} has no type because it does not exist') from e

    @property
    def externally_synced(self) -> bool:
        # This is used to be able to determine whether the playlist is automatically synced by this library
        # for the purpose of attempting to determine whether the order of items matters
        if self._externally_synced is None:
            self._externally_synced = self.name in config.externally_synced_playlists
        return self._externally_synced

    @externally_synced.setter
    def externally_synced(self, value: bool | None):
        if value is None:
            return

        self._externally_synced = value
        externally_synced_playlists = config.externally_synced_playlists
        if value:
            if self.name not in externally_synced_playlists:
                config.externally_synced_playlists = externally_synced_playlists | {self.name}  # Store -> save to file
        elif self.name in externally_synced_playlists:
            externally_synced_playlists.remove(self.name)
            config.externally_synced_playlists = externally_synced_playlists  # Store -> save to file

    @property
    def is_ordered(self) -> bool:
        # Assume that if this is not a "smart" playlist and if it is not managed via rules in this lib, then it was
        # likely configured via the web UI, and the order likely matters
        return not self.is_smart and not self.externally_synced

    @property
    def tracks(self) -> list[Track]:
        # Note: Handling for video/photo playlists is not implemented here
        if (playlist := self.playlist) and playlist.playlistType == 'audio':
            return playlist.items()
        return []

    # endregion

    # region Add / Remove Items & Sync

    def remove_items(self, items: Collection[Track], quiet: bool = False):
        """
        Remove multiple tracks from this playlist.

        The implementation in ``plexapi.playlist.Playlist.removeItems(items)`` performs an `O(n)` check for every item
        to ensure it is in the playlist before attempting to remove it.  This implementation skips that LBYL check.
        """
        if not quiet:
            self._log_change(items, 'remove')

        if self.plex.dry_run:
            return []
        elif not (playlist := self.playlist):
            raise InvalidPlaylist(f'{self} does not exist - cannot remove items from it')

        query = playlist._server.query
        del_method = playlist._server._session.delete
        results = [query(f'{playlist.key}/items/{item.playlistItemID}', method=del_method) for item in items]
        playlist.reload()
        return results

    def add_items(self, items: Collection[Track], quiet: bool = False):
        if not quiet:
            self._log_change(items, 'add')

        if self.plex.dry_run:
            return []
        elif (playlist := self.playlist) is None:
            raise InvalidPlaylist(f'{self} does not exist - cannot add items to it')

        list_type = self.type
        rating_keys = []
        for item in items:
            if item.listType != list_type:
                raise BadRequest(f'Can not mix media types when building a playlist: {list_type} and {item.listType}')
            rating_keys.append(item.ratingKey)

        rating_key_str = ','.join(map(str, rating_keys))
        # Note: plexapi uses `uri = f'{server._uriRoot()}/library/metadata/{ratingKeys}'` here, where
        # `PlexServer._uriRoot()` returns `f'server://{self.machineIdentifier}/com.plexapp.plugins.library'`
        params = {'uri': f'library://{next(iter(items)).section().uuid}/directory//library/metadata/{rating_key_str}'}
        result = playlist._server.query(f'{playlist.key}/items{joinArgs(params)}', method=playlist._server._session.put)
        playlist.reload()
        return result

    def sync_or_create(self, query: QueryResults = None, **criteria):
        if self.exists:
            self.sync(query, **criteria)
        else:
            self.create(query, **criteria)

    def sync(self, query: QueryResults = None, **criteria):
        expected = _get_tracks(self.plex, query, **criteria)
        plist_items = set(self.playlist.items())
        size = len(plist_items)
        if to_rm := plist_items.difference(expected):
            self.remove_items(to_rm)
            size -= len(to_rm)
        else:
            log.log(19, f'{self} does not contain any tracks that should be removed')

        if to_add := expected.difference(plist_items):
            self._log_change(to_add, 'add', size)
            self.add_items(to_add, quiet=True)
            size += len(to_add)
        else:
            log.log(19, f'{self} is not missing any tracks')

        if not to_add and not to_rm:
            log.info(
                f'{self} contains {size:,d} tracks and is already in sync with the given criteria', extra={'color': 11}
            )

    def _log_change(self, items: Collection[Track], verb: str, size: int = None):
        if size is None:
            size = len(self.playlist)

        num = len(items)
        new, prep, color = (size + num, 'to', 14) if verb == 'add' else (size - num, 'from', 13)
        log.info(
            f'{self.lp[verb]} {num:,d} tracks {prep} {self} ({size:,d} tracks => {new:,d}):', extra={'color': color}
        )
        print(bullet_list(items, sort=isinstance(items, set)))

    # endregion

    def compare_tracks(self, other: PlexPlaylist, strict: bool = False):
        self_tracks = set(self.playlist.items())
        other_tracks = set(other.playlist.items())
        print(f'{self} contains {len(self_tracks)} tracks, {other} contains {len(other_tracks)} tracks')
        if strict:
            removed, added = other_tracks.difference(self_tracks), self_tracks.difference(other_tracks)
        else:
            removed, added = _track_diff(other_tracks, self_tracks), _track_diff(self_tracks, other_tracks)

        if removed:
            # log.info(f'{len(removed)} tracks are in {other} but not in {self}', extra={'color': 'red'})
            log.info(f'{len(removed)} tracks were removed from {other}:', extra={'color': 'red'})
            print(colored(bullet_list(removed), 'red'))

        if added:
            # log.info(f'{len(added)} tracks are in {self} but not in {other}', extra={'color': 'green'})
            log.info(f'{len(added)} tracks were added to {self}:', extra={'color': 'green'})
            print(colored(bullet_list(added), 'green'))

        if not removed and not added:
            log.info(f'Playlists {self} and {other} are identical')

    def print_info(self, flac_color: AnsiColor = 10, other_color: AnsiColor = 9):
        tracks = self.playlist.items()
        print(f'{self} contains {len(tracks)} tracks:')
        for track in tracks:
            is_flac = track.media[0].audioCodec == 'flac'
            print(colored(f'  - {track}', flac_color if is_flac else other_color))

    def _get_info(self) -> dict[str, Any]:
        return {
            'Track count': len(self.playlist),
            'Duration': format_duration(self.playlist.duration / 1000),
            'Type': self.type,
            'Smart': self.is_smart,
            'Externally synced': self.externally_synced,
            'Is ordered': self.is_ordered,
            'Created': self.playlist.addedAt.isoformat(' '),
            'Last modified': self.playlist.updatedAt.isoformat(' '),
        }

    def pprint(self, *, show_tracks: bool = False, ok_color: AnsiColor = 10, bad_color: AnsiColor = 9):
        print(f' - {self.name}:')
        for key, val in self._get_info().items():
            print(f'   - {key}: {val}')
        if show_tracks:
            print(f'   - Tracks:')
            for track in self.tracks:
                codec = track.media[0].audioCodec
                is_flac = codec == 'flac'
                exists = track in self.plex.all_tracks
                if exists:
                    color = ok_color if is_flac and exists else bad_color
                else:
                    color = 201

                exists_str = 'exists' if exists else 'missing'
                track_str = f'[{codec:>4s}, {exists_str:>7s}] {track}'
                print(f'     - {colored(track_str, color)}')

    # region Serialization

    def dumps(self) -> PlaylistXmlDict:
        """
        Prepares this Playlist for JSON serialization.  Using XML instead is recommended because dumping to json results
        in wrapping XML strings in JSON, with all of the escaping that entails.
        """
        # Note: Using `encoding='unicode'` results in `tostring` returning a string, otherwise it would return bytes
        playlist: str = tostring(self.playlist._data, encoding='unicode')  # noqa
        tracks = [tostring(track._data, encoding='unicode') for track in self.playlist.items()]
        return {'name': self.name, 'playlist': playlist, 'tracks': tracks}

    def as_xml(self, indent: bool = False) -> Element:
        root = Element('PlexPlaylist', name=self.name)

        pl_data: Element = self.playlist._data  # noqa  # PlexObject incorrectly hints ElementTree, but it is an Element
        # The ele stored in _data has an explicit </Playlist> tag, which results in bad formatting via indent because
        # it has no children. Using a new Element lets it self-close and prevents potential modification of the original
        root.append(Element(pl_data.tag, pl_data.attrib))

        tracks = Element('Tracks')
        tracks.extend(track._data for track in self.playlist.items())
        root.append(tracks)

        if indent:
            _indent(root)
            root.tail = '\n'

        return root

    def dumps_xml(self) -> str:
        # Note: Using `encoding='unicode'` results in `tostring` returning a string, otherwise it would return bytes
        return tostring(self.as_xml(True), encoding='unicode')

    def dump(self, path: PathLike, compress: bool = True, xml: bool = False):
        from .serialization import PlaylistSerializer

        data = self.dumps_xml() if xml else self.dumps()
        PlaylistSerializer._dump(data, dst_dir=path, stem=self.name, log_name=self, compress=compress)

    @classmethod
    def dump_all(
        cls,
        dst_dir: PathLike,
        plex: OptServer = None,
        *,
        compress: bool = True,
        separate: bool = False,
        xml: bool = False,
    ):
        from .serialization import PlaylistSerializer

        PlaylistSerializer(dst_dir, plex, compress=compress, xml=xml).dump_all(separate)

    # endregion

    # region Deserialization

    @classmethod
    def loads(cls, playlist: str | PlaylistXmlDict, plex: OptServer = None) -> PlexPlaylist:
        from .serialization import PlaylistLoader

        return PlaylistLoader(plex).loads(playlist)

    @classmethod
    def load(cls, path: PathLike, plex: OptServer = None) -> PlexPlaylist:
        from .serialization import PlaylistLoader

        return PlaylistLoader(plex).load(path)

    @classmethod
    def load_all(cls, path: PathLike, plex: OptServer = None) -> dict[str, PlexPlaylist]:
        from .serialization import PlaylistLoader

        return PlaylistLoader(plex).load_all(path)

    # endregion


# region Public Functions


def compare_playlists(plex: LocalPlexServer, path: PathLike, name: str = None, strict: bool = False):
    file_playlists = PlexPlaylist.load_all(path, plex)
    if name:
        try:
            file_playlists = {name: file_playlists[name]}
        except KeyError as e:
            raise ValueError(f'Playlist {name!r} was not stored in {path}') from e

    live_playlists = plex.playlists
    for name, playlist in file_playlists.items():
        try:
            current = live_playlists[name]
        except KeyError:
            pass
        else:
            current.name += ' (current)'
            playlist.name += ' (old)'
            current.compare_tracks(playlist, strict)


# endregion


def _get_tracks(plex: LocalPlexServer, content: Tracks = None, **criteria) -> set[Track]:
    if content is not None:
        if isinstance(content, QueryResults):
            if content._type != 'track':
                raise ValueError(f'Expected track results, found {content._type!r}')
            return content.results()
        elif isinstance(content, Track):
            return {content}
        elif isinstance(next(iter(content)), Track):
            return content if isinstance(content, set) else set(content)
        else:
            raise TypeError(f'Unexpected track type={type(content).__name__!r}')
    elif criteria:
        return plex.get_tracks(**criteria)
    raise ValueError('Query results or criteria, or an iterable containing one or more tracks/items are required')


def _track_diff(a: set[Track], b: set[Track]) -> list[str]:
    """
    Considers tracks with the same ID or with the same artist name + album name + title to be the same track.

    :param a: A set of tracks
    :param b: A set of tracks
    :return: The set of tracks that are in set A that are not in set B
    """
    a_dict = {_track_key(t): (i, t) for i, t in enumerate(a, 1)}
    b_titles = {_track_key(t) for t in b}
    if title_diff := set(a_dict).difference(b_titles):
        diff_id_map = {t._int_key: (i, t) for i, t in (a_dict[k] for k in title_diff)}
        keep_ids = set(diff_id_map).difference(t._int_key for t in b)
        return ['[{:04d}] {}'.format(*diff_id_map[i]) for i in keep_ids]
    else:
        return []


def _norm_title(title: str) -> str:
    return ''.join(title.split()).casefold()


def _track_key(track: Track) -> tuple[str, str, str]:
    return _norm_title(track.grandparentTitle), _norm_title(track.parentTitle), _norm_title(track.title)
