"""
:author: Doug Skrypa
"""

import logging
import re
from typing import TypeVar, Literal

from plexapi.base import PlexPartialObject

from ds_tools.output import short_repr
from ..common.utils import stars

__all__ = [
    'PlexObj', 'PlexObjTypes', 'CUSTOM_FILTERS_BASE', 'CUSTOM_OPS', 'CUSTOM_FILTERS_TRACK_ARTIST', 'ALIASES',
    '_show_filters', '_prefixed_filters', '_resolve_aliases', '_resolve_custom_ops', 'print_song_info'
]
log = logging.getLogger(__name__)

PlexObj = TypeVar('PlexObj', bound=PlexPartialObject)
PlexObjTypes = Literal[     # SEARCHTYPES keys
    'movie', 'show', 'season', 'episode', 'trailer', 'comic', 'person', 'artist', 'album', 'track', 'picture', 'clip',
    'photo', 'photoalbum', 'playlist', 'playlistFolder', 'collection', 'userPlaylistItem'
]

CUSTOM_FILTERS_BASE = {
    'genre': ('album', 'genre__tag', {'track': 'parentKey'}),
    'album': ('album', 'title', {'track': 'parentKey'}),
    'artist': ('artist', 'title', {'album': 'parentKey'}),
    'in_playlist': ('playlist', 'title', {})
}
CUSTOM_FILTERS_TRACK_ARTIST = {
    'artist': ('artist', 'title', {'track': 'grandparentKey'}),
}
CUSTOM_OPS = {
    '__like': 'sregex',
    '__like_exact': 'sregex',
    '__not_like': 'nsregex'
}
ALIASES = {
    'rating': 'userRating'
}


def _show_filters(filters):
    final_filters = '\n'.join(f'    {key}={short_repr(val)}' for key, val in sorted(filters.items()))
    log.debug(f'Final filters:\n{final_filters}')


def _prefixed_filters(field, filters):
    us_key = '{}__'.format(field)
    return {k for k in filters if k == field or k.startswith(us_key)}


def _resolve_aliases(kwargs):
    for key, val in list(kwargs.items()):
        base = key
        op = None
        if '__' in key:
            base, op = key.split('__', maxsplit=1)
        try:
            real_key = ALIASES[base]
        except KeyError:
            pass
        else:
            del kwargs[key]
            if op:
                real_key = f'{real_key}__{op}'
            kwargs[real_key] = val
            log.debug(f'Resolved query alias={key!r} => {real_key}={short_repr(val)}')

    return kwargs


def _resolve_custom_ops(kwargs):
    # Replace custom/shorthand ops with the real operators
    for filter_key, filter_val in sorted(kwargs.items()):
        keyword = next((val for val in CUSTOM_OPS if filter_key.endswith(val)), None)
        if keyword:
            kwargs.pop(filter_key)
            target_key = '{}__{}'.format(filter_key[:-len(keyword)], CUSTOM_OPS[keyword])
            if keyword == '__like' and isinstance(filter_val, str):
                filter_val = filter_val.replace(' ', '.*?')
            filter_val = re.compile(filter_val, re.IGNORECASE) if isinstance(filter_val, str) else filter_val
            log.debug(f'Replacing custom op={filter_key!r} with {target_key}={short_repr(filter_val)}')
            kwargs[target_key] = filter_val

    return kwargs


def print_song_info(songs):
    for song in songs:
        print('{} - {} - {} - {}'.format(stars(song.userRating), song.artist().title, song.album().title, song.title))
