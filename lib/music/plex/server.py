"""
Local Plex server client implementation.

:author: Doug Skrypa
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from urllib.parse import urlencode

from plexapi import DEFAULT_CONFIG_PATH
from plexapi.exceptions import Unauthorized
from plexapi.library import Library, LibrarySection, MusicSection, ShowSection, MovieSection
from plexapi.server import PlexServer
from plexapi.utils import SEARCHTYPES, PLEXOBJECTS
from requests import Session, Response
from urllib3 import disable_warnings as disable_urllib3_warnings

from ds_tools.caching.decorators import cached_property, ClearableCachedPropertyMixin

from .config import config
from .constants import TYPE_SECTION_MAP
from .patches import apply_plex_patches
from .playlist import PlexPlaylist
from .query import QueryResults

if TYPE_CHECKING:
    from plexapi.audio import Track, Artist, Album

    from .typing import AnyLibSection, LibSection, PlexObj, PlexObjTypes

__all__ = ['LocalPlexServer']
log = logging.getLogger(__name__)

PLEX_TYPE_CLS_MAP = {cls.TYPE: cls for cls in PLEXOBJECTS.values() if cls.TYPE}

Section = MusicSection | ShowSection | MovieSection


class LocalPlexServer(ClearableCachedPropertyMixin):
    def __init__(
        self,
        url: str = None,
        user: str = None,
        *,
        server_path_root: str = None,
        config_path: str = DEFAULT_CONFIG_PATH,
        music_library: str = None,
        tv_library: str = None,
        movie_library: str = None,
        dry_run: bool = False,
        apply_patches: bool = True,
    ):
        disable_urllib3_warnings()
        if apply_patches:
            apply_plex_patches()

        config.update(
            config_path,
            dry_run=dry_run,
            url=url,
            user=user,
            server_root=server_path_root,
            music_lib_name=music_library,
            tv_lib_name=tv_library,
            movies_lib_name=movie_library,
        )
        self.user = config.user
        self.url = config.url
        self.dry_run = dry_run

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__}({self.user}@{self.url})>'

    def __eq__(self, other: LocalPlexServer) -> bool:
        return self.user == other.user and self.url == other.url

    @cached_property
    def server(self) -> PlexServer:
        session = Session()
        session.verify = False
        try:
            return PlexServer(self.url, config.token, session=session)
        except Unauthorized as e:
            log.warning(f'Token expired: {e}')
            config.reset_token()
            return PlexServer(self.url, config.token, session=session)

    def request(self, method: str, endpoint: str, **kwargs) -> Response:
        server = self.server
        url = f'{server._baseurl}/{endpoint[1:] if endpoint.startswith("/") else endpoint}'
        req_headers = server._headers()
        if headers := kwargs.pop('headers'):
            req_headers.update(headers)
        return server._session.request(method, url, headers=req_headers, **kwargs)

    @property
    def library(self) -> Library:
        return self.server.library

    # region Library Sections

    def get_lib_section(self, section: LibSection = None, obj_type: PlexObjTypes = None) -> AnyLibSection:
        if section is None:
            try:
                return self._get_primary_section(obj_type)
            except KeyError as e:
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

    def _get_primary_section(self, obj_type: PlexObjTypes = None) -> Section:
        if not obj_type:
            raise ValueError('A section and/or obj_type is required')

        section_name = TYPE_SECTION_MAP[_normalize_type(obj_type)]
        return self.primary_sections[section_name]

    @cached_property
    def sections(self) -> dict[str, AnyLibSection]:
        return {section.title: section for section in self.library.sections()}

    @cached_property
    def typed_sections(self) -> dict[str, dict[str, Section]]:
        types = {'music': MusicSection, 'tv': ShowSection, 'movies': MovieSection}
        sections = {'music': {}, 'tv': {}, 'movies': {}}
        for name, section in self.sections.items():
            if key := next((k for k, t in types.items() if isinstance(section, t)), None):
                sections[key][name] = section
        return sections

    @cached_property
    def primary_sections(self) -> dict[str, Section]:
        return {key: self.sections[name] for key, name in config.primary_lib_names.items()}

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

    def _ekey(
        self, obj_type: PlexObjTypes, section: LibSection = None, full: bool = False, check_files: bool = False
    ) -> str:
        section = self.get_lib_section(section, obj_type)
        ekey = f'/library/sections/{section.key}/all?type={SEARCHTYPES[obj_type]}'
        if full:  # Note: This doesn't end up populating the gain/loudness/etc info
            try:
                includes = PLEX_TYPE_CLS_MAP[obj_type]._INCLUDES
            except (KeyError, AttributeError):
                pass
            else:
                if not check_files:
                    includes = {k: v for k, v in includes.items() if k != 'checkFiles'}
                if includes:
                    ekey += '&' + urlencode(sorted(includes.items()))

        # log.debug(f'Resolved {obj_type=} => {ekey=}')
        return ekey

    # region Base Query Methods

    def query(self, obj_type: PlexObjTypes, section: LibSection = None, **kwargs) -> QueryResults:
        return QueryResults.new(self, _normalize_type(obj_type), section, **kwargs)

    def find_object(self, obj_type: PlexObjTypes, **kwargs) -> PlexObj | None:
        return self.query(obj_type, **kwargs).result()

    def find_objects(self, obj_type: PlexObjTypes, **kwargs) -> set[PlexObj]:
        return self.query(obj_type, **kwargs).results()

    # endregion

    # region Find Track Methods

    @cached_property
    def all_tracks(self) -> set[Track]:
        return self.get_tracks()

    def get_track(self, **kwargs) -> Track | None:
        return self.find_object('track', **kwargs)

    def get_tracks(self, **kwargs) -> set[Track]:
        return self.find_objects('track', **kwargs)

    def find_songs_by_rating_gte(self, rating: int, **kwargs) -> set[Track]:
        """
        :param rating: Song rating on a scale of 0-10
        :return: List of :class:`plexapi.audio.Track` objects
        """
        return self.get_tracks(userRating__gte=rating, **kwargs)

    def find_song_by_path(self, path: str, section: LibSection = None) -> Track | None:
        return self.get_track(media__part__file=path, section=section)

    # endregion

    # region Find Artist Methods

    def get_artists(self, name, mode='contains', **kwargs) -> set[Artist]:
        kwargs.setdefault(f'title__{mode}', name)
        return self.find_objects('artist', **kwargs)

    def get_albums(self, name, mode='contains', **kwargs) -> set[Album]:
        kwargs.setdefault(f'title__{mode}', name)
        return self.find_objects('album', **kwargs)

    # endregion

    # region Playlist Methods

    @property
    def playlists(self) -> dict[str, PlexPlaylist]:
        playlists = sorted(self.server.playlists(), key=lambda p: p.title)
        return {p.title: PlexPlaylist(p.title, self, p) for p in playlists}

    def playlist(self, name: str) -> PlexPlaylist:
        if (playlist := PlexPlaylist(name, self)).exists:
            return playlist
        raise ValueError(f'Playlist {name!r} does not exist')

    # endregion


def _normalize_type(obj_type: PlexObjTypes) -> PlexObjTypes:
    obj_type = obj_type.lower()
    if obj_type in TYPE_SECTION_MAP:
        return obj_type  # noqa
    if obj_type.endswith('s'):
        fixed = obj_type[:-1]
        if fixed in TYPE_SECTION_MAP:
            return fixed  # noqa
    raise ValueError(f'Invalid {obj_type=} - expected one of: {", ".join(sorted(TYPE_SECTION_MAP))}')
