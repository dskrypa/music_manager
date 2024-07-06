"""
Plex playlist management utilities

:author: Doug Skrypa
"""

from __future__ import annotations

import gzip
import json
import logging
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING, Collection
from xml.etree.ElementTree import tostring, fromstring

from plexapi.audio import Track
from plexapi.exceptions import BadRequest
from plexapi.playlist import Playlist
from plexapi.utils import joinArgs

from ds_tools.fs.paths import prepare_path
from ds_tools.output.color import colored
from ds_tools.output.formatting import bullet_list
from ds_tools.output.prefix import LoggingPrefix

from .exceptions import InvalidPlaylist
from .query import QueryResults

if TYPE_CHECKING:
    from music.typing import PathLike
    from .server import LocalPlexServer
    from .typing import PlaylistType

__all__ = ['PlexPlaylist', 'dump_playlists', 'compare_playlists', 'list_playlists']
log = logging.getLogger(__name__)

Tracks = Collection[Track] | QueryResults


class PlexPlaylist:
    plex: LocalPlexServer
    name: str
    lp: LoggingPrefix

    def __init__(self, name: str, plex: LocalPlexServer = None, playlist: Playlist = None):
        self.plex = _get_plex(plex)
        self.name = name
        self._playlist = playlist
        self.lp = LoggingPrefix(self.plex.dry_run)

    # region Create Playlist

    @classmethod
    def new(cls, name: str, plex: LocalPlexServer = None, content: Tracks = None, **criteria) -> PlexPlaylist:
        self = cls(name, plex)
        self.create(content, **criteria)
        return self

    def create(self, content: Tracks = None, **criteria):
        items = list(_get_tracks(self.plex, content, **criteria))
        log.info(f'{self.lp.create} {self} with {len(items):,d} tracks', extra={'color': 10})
        log.debug(f'Creating {self} with tracks: {items}')
        if not self.plex.dry_run:
            self._playlist = Playlist.create(self.plex.server, self.name, items)

    # endregion

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}({self.name!r})'

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
        try:
            return self.playlist.playlistType
        except AttributeError as e:
            raise InvalidPlaylist(f'{self} has no type because it does not exist') from e

    @property
    def tracks(self) -> list[Track]:
        # Technically, the return type would correspond with the playlist type
        if playlist := self.playlist:
            return playlist.items()
        return []

    # endregion

    # region Add / Remove Items & Sync

    def remove_items(self, items: Collection[Track], quiet: bool = False):
        """
        Remove multiple tracks from this playlist.
        Avoids calling reload after every removal when removing items in bulk.

        Original::
            for track in items:
                plist.removeItem(track)
        """
        if not quiet:
            self._log_change(items, 'remove')

        if self.plex.dry_run:
            return
        elif not (playlist := self.playlist):
            raise InvalidPlaylist(f'{self} does not exist - cannot remove items from it')

        del_method = playlist._server._session.delete
        results = [
            playlist._server.query(f'{playlist.key}/items/{item.playlistItemID}', method=del_method)
            for item in items
        ]
        playlist.reload()
        return results

    def add_items(self, items: Collection[Track], quiet: bool = False):
        if not quiet:
            self._log_change(items, 'add')

        if self.plex.dry_run:
            return
        elif (playlist := self.playlist) is None:
            raise InvalidPlaylist(f'{self} does not exist - cannot add items to it')

        list_type = self.type
        rating_keys = []
        for item in items:
            if item.listType != list_type:
                raise BadRequest(f'Can not mix media types when building a playlist: {list_type} and {item.listType}')
            rating_keys.append(item.ratingKey)

        rating_key_str = ','.join(map(str, rating_keys))
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
            msg = f'{self} contains {size:,d} tracks and is already in sync with the given criteria'
            log.info(msg, extra={'color': 11})

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

    def print_info(self, flac_color: str | int | None = None, other_color: str | int | None = 'red'):
        tracks = self.playlist.items()
        print(f'{self} contains {len(tracks)} tracks:')
        for track in tracks:
            is_flac = track.media[0].audioCodec == 'flac'
            print(colored(f'  - {track}', flac_color if is_flac else other_color))

    # region Serialization

    def dumps(self) -> dict[str, str | list[str]]:
        playlist = tostring(self.playlist._data, encoding='unicode')  # noqa
        tracks = [tostring(track._data, encoding='unicode') for track in self.playlist.items()]
        return {'playlist': playlist, 'tracks': tracks}

    def dump(self, path: PathLike, compress: bool = True):
        path = prepare_path(path, (self.name, '.json.gz' if compress else '.json'), sanitize=True, add_date=True)
        log.info(f'Saving {self} to {path.as_posix()}')
        open_func, mode = (gzip.open, 'wt') if compress else (open, 'w')
        with open_func(path, mode, encoding='utf-8') as f:
            json.dump(self.dumps(), f, indent=4, ensure_ascii=False)

    @classmethod
    def dump_all(cls, path: PathLike, plex: LocalPlexServer = None, compress: bool = True):
        playlists = {name: playlist.dumps() for name, playlist in sorted(_get_plex(plex).playlists.items())}
        path = prepare_path(path, ('all_plex_playlists', '.json.gz' if compress else '.json'), add_date=True)
        log.info(f'Saving {len(playlists)} playlists to {path.as_posix()}')
        open_func, mode = (gzip.open, 'wt') if compress else (open, 'w')
        with open_func(path, mode, encoding='utf-8') as f:
            json.dump(playlists, f, indent=4, ensure_ascii=False)

    @classmethod
    def loads(cls, playlist_data: str, track_data: Collection[str], plex: LocalPlexServer = None) -> PlexPlaylist:
        plex = _get_plex(plex)
        playlist = Playlist(plex.server, fromstring(playlist_data.encode('utf-8')))  # noqa
        playlist._items = [Track(plex.server, fromstring(td.encode('utf-8'))) for td in track_data]  # noqa
        return cls(playlist.title, plex, playlist)

    @classmethod
    def load(cls, path: PathLike, plex: LocalPlexServer = None) -> PlexPlaylist:
        path = Path(path).expanduser()
        open_func, mode = (gzip.open, 'rt') if path.suffix == '.gz' else (open, 'r')
        with open_func(path, mode, encoding='utf-8') as f:
            data = json.load(f)
        return cls.loads(data['playlist'], data['tracks'], plex)

    @classmethod
    def load_all(cls, path: PathLike, plex: LocalPlexServer = None) -> dict[str, PlexPlaylist]:
        path = Path(path).expanduser()
        open_func, mode = (gzip.open, 'rt') if path.suffix == '.gz' else (open, 'r')
        with open_func(path, mode, encoding='utf-8') as f:
            loaded = json.load(f)

        plex = _get_plex(plex)
        if len(loaded) == 2 and isinstance(loaded.get('playlist'), str) and isinstance(loaded.get('tracks'), list):
            playlist = cls.loads(loaded['playlist'], loaded['tracks'], plex)
            return {playlist.name: playlist}
        else:
            return {name: cls.loads(data['playlist'], data['tracks'], plex) for name, data in loaded.items()}

    # endregion


# region Public Functions


def dump_playlists(plex: LocalPlexServer, path: str | Path, name: str = None, compress: bool = True):
    if name:
        plex.playlist(name).dump(path, compress)
    else:
        PlexPlaylist.dump_all(path, plex, compress)


def compare_playlists(plex: LocalPlexServer, path: str | Path, name: str = None, strict: bool = False):
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


def list_playlists(plex: LocalPlexServer, path: str | Path):
    for name in sorted(PlexPlaylist.load_all(path, plex)):
        print(name)


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


def _get_plex(plex: LocalPlexServer = None) -> LocalPlexServer:
    """Workaround for the circular dependency"""
    if plex is None:
        from .server import LocalPlexServer

        plex = LocalPlexServer()

    return plex


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
