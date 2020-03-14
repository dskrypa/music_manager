"""
:author: Doug Skrypa
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .album import DiscographyEntryPart

__all__ = ['Track']
log = logging.getLogger(__name__)

PATH_FORMATS = {
    'alb_type_with_num': '{artist}/{album_type}/[{date}] {album} [{album_num}]/{num}. {track}.{ext}',
    'alb_type_no_num': '{artist}/{album_type}/[{date}] {album}/{num}. {track}.{ext}',
}


class Track:
    def __init__(self, num: int, name, album_part: 'DiscographyEntryPart'):
        self.num = num
        self.name = name
        self.album_part = album_part

    def __repr__(self):
        return f'<{self.__class__.__name__}[{self.num:02d}: {self.name!r} @ {self.album_part}]>'

    def __lt__(self, other):
        return (self.album_part, self.num, self.name) < (other.album_part, other.num, other.name)

    def format_path(self, fmt=PATH_FORMATS['alb_type_no_num'], ext='mp3'):
        album_part = self.album_part
        edition = album_part.edition
        artist = edition.artist
        if edition.edition:
            album_name = f'{edition.name} - {edition.edition}'
        else:
            album_name = str(edition.name)
        args = {
            # 'artist': artist.name.english or artist.name.non_eng,
            # TODO: Fix artist to be an Artist
            'artist': artist.show,
            'album_type': edition.type.real_name,
            'date': edition.date.strftime('%Y.%m.%d'),
            'album': album_name,
            'album_num': None,
            'num': self.num,
            'track': self.name,
            'ext': ext
        }
        return fmt.format(**args)
