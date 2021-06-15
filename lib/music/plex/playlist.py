"""
Plex playlist management utilities

:author: Doug Skrypa
"""

import gzip
import json
import logging
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING, Union, Collection, Optional
from xml.etree.ElementTree import tostring, fromstring

from plexapi.audio import Track
from plexapi.exceptions import BadRequest
from plexapi.playlist import Playlist
from plexapi.utils import joinArgs

from ds_tools.fs.paths import prepare_path, PathLike
from ds_tools.output.color import colored
from ds_tools.output.formatting import bullet_list
from .exceptions import InvalidPlaylist
from .query import QueryResults

if TYPE_CHECKING:
    from .server import LocalPlexServer

__all__ = ['PlexPlaylist']
log = logging.getLogger(__name__)
Tracks = Union[Collection[Track], QueryResults]


class PlexPlaylist:
    def __init__(self, name: str, server: 'LocalPlexServer' = None, playlist: Playlist = None):
        self.server = _get_server(server)
        self.name = name
        self._playlist = playlist

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}({self.name!r})'

    @property
    def playlist(self) -> Optional[Playlist]:
        if self._playlist is None:
            playlists = self.server._session.playlists()
            if (playlist := next((p for p in playlists if p.title == self.name), None)) is not None:
                self._playlist = playlist
            else:
                lc_name = self.name.lower()
                if (playlist := next((p for p in playlists if p.title.lower() == lc_name), None)) is not None:
                    self._playlist = playlist
                    self.name = playlist.title
        return self._playlist

    @property
    def exists(self):
        return self.playlist is not None

    @classmethod
    def new(cls, name: str, server: 'LocalPlexServer' = None, content: Tracks = None, **criteria) -> 'PlexPlaylist':
        self = cls(name, server)
        self.create(content, **criteria)
        return self

    def create(self, content: Tracks = None, **criteria):
        items = list(_get_tracks(self.server, content, **criteria))
        prefix = '[DRY RUN] Would create' if self.server.dry_run else 'Creating'
        log.info(f'{prefix} {self} with {len(items):,d} tracks', extra={'color': 10})
        log.debug(f'Creating {self} with tracks: {items}')
        if not self.server.dry_run:
            self._playlist = Playlist.create(self.server._session, self.name, items)

    @cached_property
    def type(self):
        try:
            return self.playlist.playlistType
        except AttributeError:
            raise InvalidPlaylist(f'{self} has no type because it does not exist')

    def _log_change(self, items: Collection[Track], adding: bool, size: int = None):
        size = len(self.playlist) if size is None else size
        dry_run = self.server.dry_run
        prefix = f'[DRY RUN] Would {"add" if adding else "remove"}' if dry_run else ('Adding' if adding else 'Removing')
        num = len(items)
        new, prep, color = (size + num, 'to', 14) if adding else (size - num, 'from', 13)
        log.info(f'{prefix} {num:,d} tracks {prep} {self} ({size:,d} tracks => {new:,d}):', extra={'color': color})
        print(bullet_list(items))

    def remove_items(self, items: Collection[Track], quiet: bool = False):
        """
        Remove multiple tracks from this playlist.
        Avoids calling reload after every removal when removing items in bulk.

        Original::
            for track in items:
                plist.removeItem(track)
        """
        if not quiet:
            self._log_change(items, False)
        if self.server.dry_run:
            return
        if not (playlist := self.playlist):
            raise InvalidPlaylist(f'{self} does not exist - cannot remove items from it')
        del_method = playlist._server._session.delete
        uri_fmt = '{}/items/{{}}'.format(playlist.key)
        results = [playlist._server.query(uri_fmt.format(item.playlistItemID), method=del_method) for item in items]
        playlist.reload()
        return results

    def add_items(self, items: Collection[Track], quiet: bool = False):
        if not quiet:
            self._log_change(items, True)
        if self.server.dry_run:
            return
        if (playlist := self.playlist) is None:
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

    def sync(self, query: QueryResults = None, **criteria):
        expected = _get_tracks(self.server, query, **criteria)
        plist = self.playlist
        plist_items = set(plist.items())
        size = len(plist_items)
        if to_rm := plist_items.difference(expected):
            self.remove_items(to_rm)
            size -= len(to_rm)
        else:
            log.log(19, f'{self} does not contain any tracks that should be removed')

        if to_add := expected.difference(plist_items):
            self._log_change(to_add, True, size)
            self.add_items(to_add, quiet=True)
            size += len(to_add)
        else:
            log.log(19, f'{self} is not missing any tracks')

        if not to_add and not to_rm:
            msg = f'{self} contains {size:,d} tracks and is already in sync with the given criteria'
            log.info(msg, extra={'color': 11})

    def compare_tracks(self, other: 'PlexPlaylist', strict: bool = False):
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

    # region Serialization

    def dumps(self) -> dict[str, Union[str, list[str]]]:
        playlist = tostring(self.playlist._data, encoding='unicode')
        tracks = [tostring(track._data, encoding='unicode') for track in self.playlist.items()]
        return {'playlist': playlist, 'tracks': tracks}

    def dump(self, path: PathLike, compress: bool = True):
        path = prepare_path(path, (self.name, '.json.gz' if compress else '.json'), sanitize=True)
        log.info(f'Saving {self} to {path.as_posix()}')
        open_func, mode = (gzip.open, 'wt') if compress else (open, 'w')
        with open_func(path, mode, encoding='utf-8') as f:
            json.dump(self.dumps(), f, indent=4, sort_keys=True)

    @classmethod
    def dump_all(cls, path: PathLike, server: 'LocalPlexServer' = None, compress: bool = True):
        playlists = {name: playlist.dumps() for name, playlist in _get_server(server).playlists.items()}
        path = prepare_path(path, ('all_plex_playlists', '.json.gz' if compress else '.json'))
        log.info(f'Saving {len(playlists)} playlists to {path.as_posix()}')
        open_func, mode = (gzip.open, 'wt') if compress else (open, 'w')
        with open_func(path, mode, encoding='utf-8') as f:
            json.dump(playlists, f, indent=4, sort_keys=True)

    @classmethod
    def loads(cls, playlist_data: str, track_data: Collection[str], server: 'LocalPlexServer' = None) -> 'PlexPlaylist':
        server = _get_server(server)
        playlist = Playlist(server._session, fromstring(playlist_data.encode('utf-8')))
        playlist._items = [Track(server._session, fromstring(td.encode('utf-8'))) for td in track_data]
        return cls(playlist.title, server, playlist)

    @classmethod
    def load(cls, path: PathLike, server: 'LocalPlexServer' = None) -> 'PlexPlaylist':
        path = Path(path).expanduser()
        open_func, mode = (gzip.open, 'rt') if path.suffix == '.gz' else (open, 'r')
        with open_func(path, mode, encoding='utf-8') as f:
            data = json.load(f)
        return cls.loads(data['playlist'], data['tracks'], server)

    @classmethod
    def load_all(cls, path: PathLike, server: 'LocalPlexServer' = None) -> dict[str, 'PlexPlaylist']:
        path = Path(path).expanduser()
        open_func, mode = (gzip.open, 'rt') if path.suffix == '.gz' else (open, 'r')
        with open_func(path, mode, encoding='utf-8') as f:
            loaded = json.load(f)

        server = _get_server(server)
        if len(loaded) == 2 and isinstance(loaded.get('playlist'), str) and isinstance(loaded.get('tracks'), list):
            playlist = cls.loads(loaded['playlist'], loaded['tracks'], server)
            return {playlist.name: playlist}
        else:
            return {name: cls.loads(data['playlist'], data['tracks'], server) for name, data in loaded.items()}

    # endregion


def _get_tracks(server: 'LocalPlexServer', content: Tracks = None, **criteria) -> set[Track]:
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
        return server.get_tracks(**criteria)
    raise ValueError('Query results or criteria, or an iterable containing one or more tracks/items are required')


def _get_server(server: 'LocalPlexServer' = None) -> 'LocalPlexServer':
    """Workaround for the circular dependency"""
    if server is None:
        from .server import LocalPlexServer
        server = LocalPlexServer()
    return server


def _track_diff(a: set[Track], b: set[Track]) -> set[Track]:
    """
    Considers tracks with the same ID or with the same artist name + album name + title to be the same track.

    :param a: A set of tracks
    :param b: A set of tracks
    :return: The set of tracks that are in set A that are not in set B
    """
    a_dict = {(t.grandparentTitle, t.parentTitle, t.title): t for t in a}
    b_titles = {(t.grandparentTitle, t.parentTitle, t.title) for t in b}
    if title_diff := set(a_dict).difference(b_titles):
        diff_id_map = {t._int_key: t for t in (a_dict[k] for k in title_diff)}
        keep_ids = set(diff_id_map).difference(t._int_key for t in b)
        return {diff_id_map[i] for i in keep_ids}
    else:
        return set()
