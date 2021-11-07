"""
Local Plex server client implementation.

:author: Doug Skrypa
"""

import logging
from configparser import NoSectionError
from functools import cached_property
from pathlib import Path
from typing import Optional, Union

from plexapi import PlexConfig, DEFAULT_CONFIG_PATH
from plexapi.audio import Track, Artist, Album
from plexapi.exceptions import Unauthorized
from plexapi.library import Library, LibrarySection, MusicSection, ShowSection, MovieSection
from plexapi.myplex import MyPlexAccount
from plexapi.server import PlexServer
from plexapi.utils import SEARCHTYPES
from requests import Session, Response
from urllib3 import disable_warnings as disable_urllib3_warnings

from ..common.prompts import get_input, getpass, UIMode
from .constants import TYPE_SECTION_MAP
from .patches import apply_plex_patches
from .playlist import PlexPlaylist
from .query import QueryResults
from .typing import PlexObjTypes, PlexObj, LibSection

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
        tv_library: str = None,
        movie_library: str = None,
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
        libs = {'music': (music_library, 'Music'), 'tv': (tv_library, 'TV Shows'), 'movies': (movie_library, 'Movies')}
        self.primary_lib_names = {
            k: self._get_config('custom', f'{k}_lib_name', new_value=name) or d for k, (name, d) in libs.items()
        }
        self.dry_run = dry_run

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__}({self.user}@{self.url})>'

    def __eq__(self, other) -> bool:
        return self.user == other.user and self.url == other.url

    # region Configs

    @cached_property
    def _token(self) -> str:
        token = self._get_config('auth', 'server_token')
        if not token:
            if UIMode.current() == UIMode.GUI:
                prompt = (
                    f'Please enter the Plex password for account={self.user}\n'
                    f'Note: your password will not be stored - it will only be used to obtain a server token.\n'
                    f'That token will be stored in {self._config_path.as_posix()}'
                )
            else:
                prompt = 'Plex password:'
            if password := getpass(prompt, title='Plex Manager - Authentication Required'):
                account = MyPlexAccount(self.user, password)
                del password
            else:
                raise RuntimeError('Password was not provided')
            token = account._token
            self._set_config('auth', 'server_token', token)
        return token

    def _get_config(self, section: str, key: str, name: str = None, new_value=None, required: bool = False):
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

    def _set_config(self, section: str, key: str, value):
        try:
            self._config.set(section, key, value)
        except NoSectionError:
            self._config.add_section(section)
            self._config.set(section, key, value)
        log.debug(f'Saving Plex config to {self._config_path.as_posix()}')
        with self._config_path.open('w', encoding='utf-8') as f:
            self._config.write(f)

    # endregion

    @cached_property
    def server(self) -> PlexServer:
        session = Session()
        session.verify = False
        try:
            return PlexServer(self.url, self._token, session=session)
        except Unauthorized as e:
            log.warning(f'Token expired: {e}')
            log.debug(f'Deleting old token from config in {self._config_path.as_posix()}')
            self._config.remove_option('auth', 'server_token')
            with self._config_path.open('w', encoding='utf-8') as f:
                self._config.write(f)
            del self.__dict__['_token']
            return PlexServer(self.url, self._token, session=session)

    def request(self, method: str, endpoint: str, **kwargs) -> Response:
        server = self.server
        url = f'{server._baseurl}/{endpoint[1:] if endpoint.startswith("/") else endpoint}'
        return server._session.request(method, url, headers=server._headers(), **kwargs)

    @property
    def library(self) -> Library:
        return self.server.library

    # region Library Sections

    def get_lib_section(self, section: LibSection = None, obj_type: PlexObjTypes = None) -> LibrarySection:
        if section is None:
            try:
                return self.primary_sections[TYPE_SECTION_MAP[obj_type]]
            except KeyError as e:
                if obj_type is None:
                    raise ValueError('A section and/or obj_type is required') from None
                raise ValueError(f'A section is required for {obj_type=}') from e
        elif isinstance(section, LibrarySection):
            return section
        elif isinstance(section, str):
            return self.library.section(section)
        elif isinstance(section, int):
            for lib_section in self.sections.values():
                if lib_section.key == section:
                    return lib_section
            raise ValueError(f'No lib section found for {section=}')
        else:
            raise TypeError(f'Unexpected lib section type={type(section)}')

    @cached_property
    def sections(self) -> dict[str, LibrarySection]:
        return {section.title: section for section in self.library.sections()}

    @cached_property
    def typed_sections(self) -> dict[str, dict[str, LibrarySection]]:
        types = {'music': MusicSection, 'tv': ShowSection, 'movies': MovieSection}
        sections = {'music': {}, 'tv': {}, 'movies': {}}
        for name, section in self.sections.items():
            if key := next((k for k, t in types.items() if isinstance(section, t)), None):
                sections[key][name] = section
        return sections

    @cached_property
    def primary_sections(self) -> dict[str, Union[MusicSection, ShowSection, MovieSection]]:
        return {key: self.sections[name] for key, name in self.primary_lib_names.items()}

    @cached_property
    def music(self) -> MusicSection:
        return self.primary_sections['music']

    @cached_property
    def tv(self) -> ShowSection:
        return self.primary_sections['tv']

    @cached_property
    def movies(self) -> MovieSection:
        return self.primary_sections['movies']

    # endregion

    def _ekey(self, obj_type: PlexObjTypes, section: LibSection = None) -> str:
        section = self.get_lib_section(section, obj_type)
        ekey = f'/library/sections/{section.key}/all?type={SEARCHTYPES[obj_type]}'
        # log.debug(f'Resolved {obj_type=!r} => {ekey=!r}')
        return ekey

    def find_songs_by_rating_gte(self, rating: int, **kwargs) -> set[Track]:
        """
        :param rating: Song rating on a scale of 0-10
        :return: List of :class:`plexapi.audio.Track` objects
        """
        return self.get_tracks(userRating__gte=rating, **kwargs)

    def find_song_by_path(self, path: str, section: LibSection = None) -> Optional[Track]:
        return self.get_track(media__part__file=path, section=section)

    def get_artists(self, name, mode='contains', **kwargs) -> set[Artist]:
        kwargs.setdefault('title__{}'.format(mode), name)
        return self.find_objects('artist', **kwargs)

    def get_albums(self, name, mode='contains', **kwargs) -> set[Album]:
        kwargs.setdefault('title__{}'.format(mode), name)
        return self.find_objects('album', **kwargs)

    def find_object(self, obj_type: PlexObjTypes, **kwargs) -> Optional[PlexObj]:
        return self.query(obj_type, **kwargs).result()

    def find_objects(self, obj_type: PlexObjTypes, **kwargs) -> set[PlexObj]:
        return self.query(obj_type, **kwargs).results()

    def get_track(self, **kwargs) -> Optional[Track]:
        return self.find_object('track', **kwargs)

    def get_tracks(self, **kwargs) -> set[Track]:
        return self.find_objects('track', **kwargs)

    def query(self, obj_type: PlexObjTypes, section: LibSection = None, **kwargs) -> QueryResults:
        return QueryResults.new(self, obj_type, section, **kwargs)

    @property
    def playlists(self) -> dict[str, PlexPlaylist]:
        return {p.title: PlexPlaylist(p.title, self, p) for p in self.server.playlists()}

    def playlist(self, name: str) -> PlexPlaylist:
        if (playlist := PlexPlaylist(name, self)).exists:
            return playlist
        raise ValueError(f'Playlist {name!r} does not exist')
