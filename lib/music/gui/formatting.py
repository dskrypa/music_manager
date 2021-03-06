"""
Formatting helper functions.

:author: Doug Skrypa
"""

import logging
from io import BytesIO
from typing import TYPE_CHECKING

from PySimpleGUI import Text, Input, Image, Multiline

from ds_tools.caching import cached
from ..constants import typed_tag_name_map
from ..files.track.track import SongFile

if TYPE_CHECKING:
    from PIL import Image as PilImage

__all__ = ['get_track_data', 'get_cover_image']
log = logging.getLogger(__name__)


def get_track_data(track: SongFile):
    tag_name_map = typed_tag_name_map.get(track.tag_type, {})
    rows = []
    longest = 0
    track_id = id(track)
    for i, (tag, val) in enumerate(sorted(track.tags.items())):
        tag_name = tag_name_map.get(tag[:4], tag)
        if tag_name == 'Album Cover':
            continue

        tag_key = f'tag_{track_id}_{i}'
        val_key = f'val_{track_id}_{i}'
        longest = max(longest, len(tag_name))
        if tag_name == 'Lyrics':
            rows.append([Text(tag_name, key=tag_key), Multiline(val, size=(45, 4), key=val_key)])
        else:
            rows.append([Text(tag_name, key=tag_key), Input(val, key=val_key)])

    for row in rows:
        row[0].Size = (longest, 1)

    return rows


def get_cover_image(track: SongFile, size: tuple[int, int] = (250, 250)) -> Image:
    key = f'img_{id(track)}'
    try:
        image = track.get_cover_image()
    except Exception as e:
        log.error(f'Unable to load cover image for {track}')
        return Image(size=size, key=key)
    else:
        return Image(data=_get_cover_image(image, size), size=size, key=key)


def _image_cache_key(image: 'PilImage.Image', size: tuple[int, int] = (250, 250)):
    return size, image.__class__, image.size, hash(image.tobytes())


@cached(True, key=_image_cache_key)
def _get_cover_image(image: 'PilImage.Image', size: tuple[int, int] = (250, 250)) -> bytes:
    image.thumbnail(size)
    bio = BytesIO()
    image.save(bio, format='PNG')
    return bio.getvalue()
