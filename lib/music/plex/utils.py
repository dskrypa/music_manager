"""
:author: Doug Skrypa
"""

import logging
from typing import Literal, Union

from plexapi.audio import Audio, Album, Artist, Track
from plexapi.playlist import Playlist
from plexapi.video import Video, Movie, Show, Season, Episode

from ds_tools.output import short_repr
from ..common.utils import stars

__all__ = ['PlexObj', 'PlexObjTypes', '_prefixed_filters', 'print_song_info', '_filter_repr']
log = logging.getLogger(__name__)

PlexObj = Union[Album, Artist, Audio, Track, Playlist, Video, Movie, Show, Season, Episode]
# PlexObj = TypeVar('PlexObj', bound=PlexPartialObject)
PlexObjTypes = Literal[     # SEARCHTYPES keys
    'movie', 'show', 'season', 'episode', 'trailer', 'comic', 'person', 'artist', 'album', 'track', 'picture', 'clip',
    'photo', 'photoalbum', 'playlist', 'playlistFolder', 'collection', 'userPlaylistItem'
]


def _filter_repr(filters):
    return ', '.join('{}={}'.format(k, short_repr(v)) for k, v in filters.items())


def _prefixed_filters(field, filters):
    us_key = '{}__'.format(field)
    return {k for k in filters if k == field or k.startswith(us_key)}


def print_song_info(songs):
    for song in songs:
        print('{} - {} - {} - {}'.format(stars(song.userRating), song.artist().title, song.album().title, song.title))
