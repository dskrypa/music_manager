"""
:author: Doug Skrypa
"""

import logging
from pathlib import Path
from typing import Literal, Union, Iterable

from plexapi.audio import Audio, Album, Artist, Track
from plexapi.library import LibrarySection
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
LibSection = Union[str, int, LibrarySection]

StrOrStrs = Union[str, Iterable[str]]
PathLike = Union[str, Path]
