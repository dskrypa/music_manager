"""
Local Plex server client implementation.

:author: Doug Skrypa
"""

import logging
from configparser import NoSectionError
from functools import cached_property
from pathlib import Path
from typing import Optional, Iterable

from plexapi import PlexConfig, DEFAULT_CONFIG_PATH
from plexapi.audio import Track, Artist, Album
from plexapi.library import MusicSection, Library
from plexapi.myplex import MyPlexAccount
from plexapi.playlist import Playlist
from plexapi.server import PlexServer
from plexapi.utils import SEARCHTYPES
from requests import Session
from urllib3 import disable_warnings as disable_urllib3_warnings

from ds_tools.output import bullet_list
from ..common.prompts import get_input, getpass
from ..files.track.track import SongFile
from .patches import apply_plex_patches
from .query import QueryResults
from .typing import PlexObjTypes, PlexObj

__all__ = ['LocalPlexServer']
log = logging.getLogger(__name__)


class LocalPlexServer:
    def __init__(
        self,
        url: str = None,
        user: str = None,
        server_path_root: str = None,
        config_path: str = DEFAULT_CONFIG_PATH,
        music_library: str = None,
        dry_run: bool = False,
    ):
        disable_urllib3_warnings()
        apply_plex_patches()
        self._config_path = Path(config_path).expanduser().resolve()
        log.debug(f'Reading PlexAPI config from {self._config_path}')
        if not self._config_path.exists():
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            self._config_path.touch()
        self._config = PlexConfig(self._config_path)  # noqa
        self.url = self._get_config('auth', 'server_baseurl', 'server url', url, required=True)
        need_user = not self._config.get('auth.server_token')
        self.user = self._get_config('auth', 'myplex_username', 'username', user, required=need_user)
        server_path_root = self._get_config('custom', 'server_path_root', new_value=server_path_root)
        self.server_root = Path(server_path_root) if server_path_root else None
        self.music_library = self._get_config('custom', 'music_lib_name', new_value=music_library) or 'Music'
        self.dry_run = dry_run

    def __repr__(self):
        return f'<{self.__class__.__name__}({self.user}@{self.url})>'

    def __eq__(self, other):
        return self.user == other.user and self.url == other.url

    @cached_property
    def _token(self):
        token = self._get_config('auth', 'server_token')
        if not token:
            account = MyPlexAccount(self.user, getpass('Plex password:'))
            token = account._token
            self._set_config('auth', 'server_token', token)
        return token

    def _get_config(self, section, key, name=None, new_value=None, required=False):
        name = name or key
        cfg_value = self._config.get(f'{section}.{key}')
        if cfg_value and new_value:
            msg = f'Found {name}={cfg_value!r} in {self._config_path} - overwrite with {name}={new_value!r}?'
            if get_input(msg):
                self._set_config(section, key, new_value)
        elif required and not cfg_value and not new_value:
            try:
                new_value = get_input(f'Please enter your Plex {name}: ', parser=lambda s: s.strip() if s else s)
            except EOFError as e:
                raise RuntimeError('Unable to read stdin (this is often caused by piped input)') from e
            if not new_value:
                raise ValueError(f'Invalid {name}')
            self._set_config(section, key, new_value)
        return new_value or cfg_value

    def _set_config(self, section, key, value):
        try:
            self._config.set(section, key, value)
        except NoSectionError:
            self._config.add_section(section)
            self._config.set(section, key, value)
        with self._config_path.open('w', encoding='utf-8') as f:
            self._config.write(f)

    @cached_property
    def _session(self) -> PlexServer:
        session = Session()
        session.verify = False
        return PlexServer(self.url, self._token, session=session)

    @property
    def _library(self) -> Library:
        return self._session.library

    @cached_property
    def music(self) -> MusicSection:
        return self._library.section(self.music_library)

    def _ekey(self, search_type: PlexObjTypes) -> str:
        ekey = f'/library/sections/1/all?type={SEARCHTYPES[search_type]}'
        # log.debug(f'Resolved {search_type=!r} => {ekey=!r}')
        return ekey

    def find_songs_by_rating_gte(self, rating: int, **kwargs) -> set[Track]:
        """
        :param rating: Song rating on a scale of 0-10
        :return: List of :class:`plexapi.audio.Track` objects
        """
        return self.get_tracks(userRating__gte=rating, **kwargs)

    def find_song_by_path(self, path: str) -> Optional[Track]:
        return self.get_track(media__part__file=path)

    def get_artists(self, name, mode='contains', **kwargs) -> set[Artist]:
        kwargs.setdefault('title__{}'.format(mode), name)
        return self.find_objects('artist', **kwargs)

    def get_albums(self, name, mode='contains', **kwargs) -> set[Album]:
        kwargs.setdefault('title__{}'.format(mode), name)
        return self.find_objects('album', **kwargs)

    def find_object(self, obj_type: PlexObjTypes, **kwargs) -> Optional[PlexObj]:
        return self.query(obj_type).filter(**kwargs).result()

    def find_objects(self, obj_type: PlexObjTypes, **kwargs) -> set[PlexObj]:
        return self.query(obj_type, **kwargs).results()

    def get_track(self, **kwargs) -> Optional[Track]:
        return self.find_object('track', **kwargs)

    def get_tracks(self, **kwargs) -> set[Track]:
        return self.find_objects('track', **kwargs)

    def query(self, obj_type: PlexObjTypes, **kwargs) -> QueryResults:
        data = self.music._server.query(self._ekey(obj_type))
        return QueryResults(self, obj_type, data).filter(**kwargs)

    @property
    def playlists(self) -> dict[str, Playlist]:
        return {p.title: p for p in self._session.playlists()}

    def playlist(self, name: str) -> Playlist:
        playlists = self.playlists
        if playlist := playlists.get(name):
            return playlist
        lc_name = name.lower()
        if playlist := next((p for n, p in playlists.items() if n.lower() == lc_name), None):
            return playlist
        raise ValueError(f'Playlist {name!r} does not exist')

    def create_playlist(self, name: str, items: Iterable[Track]) -> Playlist:
        if not items:
            raise ValueError('An iterable containing one or more tracks/items must be provided')
        elif not isinstance(items, (Track, list, tuple)):   # Workaround overly strict type checking by Playlist._create
            items = list(items)

        prefix = '[DRY RUN] Would create' if self.dry_run else 'Creating'
        log.info(f'{prefix} playlist={name!r} with {len(items):,d} tracks')
        if not self.dry_run:
            return Playlist.create(self._session, name, items)

    def sync_playlist(self, name: str, *, query: Optional[QueryResults] = None, **criteria):
        if query is not None:
            if query._type != 'track':
                raise ValueError(f'Expected track results, found {query._type!r}')
            expected = query.results()
        else:
            expected = self.get_tracks(**criteria)

        try:
            plist = self.playlists[name]
        except KeyError:
            log.info(f'Creating playlist {name} with {len(expected):,d} tracks', extra={'color': 10})
            log.debug(f'Creating playlist {name} with tracks: {expected}')
            plist = self.create_playlist(name, expected)
        else:
            plist_items = set(plist.items())
            size = len(plist_items)
            if to_rm := plist_items.difference(expected):
                prefix = '[DRY RUN] Would remove' if self.dry_run else 'Removing'
                rm_fmt = '{} {:,d} tracks from playlist {} ({:,d} tracks => {:,d}):'
                log.info(rm_fmt.format(prefix, len(to_rm), name, size, size - len(to_rm)), extra={'color': 13})
                print(bullet_list(to_rm))
                size -= len(to_rm)
                if not self.dry_run:
                    plist.removeItems(to_rm)  # method added via music.plex.patches.apply_plex_patches
            else:
                log.log(19, f'Playlist {name} does not contain any tracks that should be removed')

            if to_add := expected.difference(plist_items):
                prefix = '[DRY RUN] Would add' if self.dry_run else 'Adding'
                add_fmt = '{} {:,d} tracks to playlist {} ({:,d} tracks => {:,d}):'
                log.info(add_fmt.format(prefix, len(to_add), name, size, size + len(to_add)), extra={'color': 14})
                print(bullet_list(to_add))
                if not self.dry_run:
                    plist.addItems(list(to_add))
                size += len(to_add)
            else:
                log.log(19, f'Playlist {name} is not missing any tracks')

            if not to_add and not to_rm:
                fmt = 'Playlist {} contains {:,d} tracks and is already in sync with the given criteria'
                log.info(fmt.format(name, len(plist_items)), extra={'color': 11})

    def sync_ratings_to_files(self, path_filter: str = None):
        """
        Sync the song ratings from this Plex server to the files

        :param path_filter: String that file paths must contain to be sync'd
        """
        if self.server_root is None:
            raise ValueError(f'The custom.server_path_root is missing from {self._config_path} and wasn\'t provided')
        prefix = '[DRY RUN] Would update' if self.dry_run else 'Updating'
        kwargs = {'media__part__file__icontains': path_filter} if path_filter else {}
        for track in self.find_songs_by_rating_gte(1, **kwargs):
            file = SongFile.for_plex_track(track, self.server_root)
            file_stars = file.star_rating_10
            plex_stars = track.userRating
            if file_stars == plex_stars:
                log.log(9, 'Rating is already correct for {}'.format(file))
            else:
                log.info('{} rating from {} to {} for {}'.format(prefix, file_stars, plex_stars, file))
                if not self.dry_run:
                    file.star_rating_10 = plex_stars

    def sync_ratings_from_files(self, path_filter: str = None):
        """
        Sync the song ratings on this Plex server with the ratings in the files

        :param path_filter: String that file paths must contain to be sync'd
        """
        if self.server_root is None:
            raise ValueError(f'The custom.server_path_root is missing from {self._config_path} and wasn\'t provided')
        prefix = '[DRY RUN] Would update' if self.dry_run else 'Updating'
        kwargs = {'media__part__file__icontains': path_filter} if path_filter else {}
        for track in self.get_tracks(**kwargs):
            file = SongFile.for_plex_track(track, self.server_root)
            file_stars = file.star_rating_10
            if file_stars is not None:
                plex_stars = track.userRating
                if file_stars == plex_stars:
                    log.log(9, 'Rating is already correct for {}'.format(file))
                else:
                    log.info('{} rating from {} to {} for {}'.format(prefix, plex_stars, file_stars, file))
                    if not self.dry_run:
                        track.edit(**{'userRating.value': file_stars})
