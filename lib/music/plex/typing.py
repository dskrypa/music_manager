"""
:author: Doug Skrypa
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal, Union, Iterable, Any

from plexapi.audio import Audio, Album, Artist, Track
from plexapi.library import LibrarySection, MusicSection, ShowSection, MovieSection, PhotoSection
from plexapi.playlist import Playlist
from plexapi.video import Video, Movie, Show, Season, Episode

__all__ = ['PlexObj', 'PlexObjTypes']
log = logging.getLogger(__name__)

PlexObj = Union[Album, Artist, Audio, Track, Playlist, Video, Movie, Show, Season, Episode]
# PlexObj = TypeVar('PlexObj', bound=PlexPartialObject)
PlexObjTypes = Literal[     # SEARCHTYPES keys
    'movie', 'show', 'season', 'episode', 'trailer', 'comic', 'person', 'artist', 'album', 'track', 'picture', 'clip',
    'photo', 'photoalbum', 'playlist', 'playlistFolder', 'collection', 'userPlaylistItem'
]
AnyLibSection = LibrarySection | MusicSection | ShowSection | MovieSection | PhotoSection
LibSection = Union[str, int, AnyLibSection]
PlaylistType = Literal['audio', 'video', 'photo']

Bool = Union[bool, Any]
PathLike = Union[str, Path]
StrOrStrs = Union[str, Iterable[str]]

AnsiColor = str | int | None
