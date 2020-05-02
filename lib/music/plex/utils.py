"""
:author: Doug Skrypa
"""

import logging
from typing import TypeVar, Literal

from plexapi.base import PlexPartialObject

from ds_tools.output import short_repr
from ..common.utils import stars

__all__ = ['PlexObj', 'PlexObjTypes', '_show_filters', '_prefixed_filters', 'print_song_info', '_filter_repr']
log = logging.getLogger(__name__)

PlexObj = TypeVar('PlexObj', bound=PlexPartialObject)
PlexObjTypes = Literal[     # SEARCHTYPES keys
    'movie', 'show', 'season', 'episode', 'trailer', 'comic', 'person', 'artist', 'album', 'track', 'picture', 'clip',
    'photo', 'photoalbum', 'playlist', 'playlistFolder', 'collection', 'userPlaylistItem'
]


def _filter_repr(filters):
    return ', '.join('{}={}'.format(k, short_repr(v)) for k, v in filters.items())


def _show_filters(obj_type, filters):
    final_filters = '\n'.join(f'    {key}={short_repr(val)}' for key, val in sorted(filters.items()))
    log.debug(f'Applying the following filters to {obj_type}s:\n{final_filters}')


def _prefixed_filters(field, filters):
    us_key = '{}__'.format(field)
    return {k for k in filters if k == field or k.startswith(us_key)}


def print_song_info(songs):
    for song in songs:
        print('{} - {} - {} - {}'.format(stars(song.userRating), song.artist().title, song.album().title, song.title))
