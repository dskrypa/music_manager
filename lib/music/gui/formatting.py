"""
Formatting helper functions.

:author: Doug Skrypa
"""

import logging
from io import BytesIO
from typing import Tuple

from PySimpleGUI import Text, Input, Image, Multiline

from ..constants import typed_tag_name_map
from ..files.track.track import SongFile

__all__ = ['get_track_data', 'get_cover_image']
log = logging.getLogger(__name__)


def get_track_data(track: SongFile):
    tag_name_map = typed_tag_name_map.get(track.tag_type, {})
    rows = []
    longest = 0
    for tag, val in sorted(track.tags.items()):
        tag_name = tag_name_map.get(tag[:4], tag)
        if tag_name == 'Album Cover':
            continue

        longest = max(longest, len(tag_name))
        if tag_name == 'Lyrics':
            rows.append([Text(tag_name), Multiline(val, size=(45, 4))])
        else:
            rows.append([Text(tag_name), Input(val)])

    for row in rows:
        row[0].Size = (longest, 1)

    return rows


def get_cover_image(track: SongFile, size: Tuple[int, int] = (250, 250)) -> Image:
    try:
        image = track.get_cover_image()
    except Exception as e:
        log.error(f'Unable to load cover image for {track}')
        return Image(size=size)
    else:
        image.thumbnail((250, 250))
        bio = BytesIO()
        image.save(bio, format='PNG')
        return Image(data=bio.getvalue(), size=size)
