"""
:author: Doug Skrypa
"""

import logging
from functools import partialmethod
from typing import TYPE_CHECKING

from ..text.name import Name

if TYPE_CHECKING:
    from .album import DiscographyEntryPart

__all__ = ['Track']
log = logging.getLogger(__name__)

PATH_FORMATS = {
    'alb_type_with_num': '{artist}/{album_type}/[{date}] {album} [{album_num}]/{num}. {track}.{ext}',
    'alb_type_no_num': '{artist}/{album_type}/[{date}] {album}/{num}. {track}.{ext}',
}


class Track:
    def __init__(self, num: int, name: Name, album_part: 'DiscographyEntryPart'):
        self.num = num
        self.name = name
        self.album_part = album_part

    def _repr(self, long=False):
        if long:
            return f'<{self.__class__.__name__}[{self.num:02d}: {self.name!r} @ {self.album_part}]>'
        return f'<{self.__class__.__name__}[{self.num:02d}: {self.name!r}]>'

    __repr__ = partialmethod(_repr, True)

    def __lt__(self, other: 'Track'):
        return (self.album_part, self.num, self.name) < (other.album_part, other.num, other.name)

    def full_name(self, collabs=True) -> str:
        """
        :param bool collabs: Whether collaborators / featured artists should be included
        :return str: This track's full name
        """
        name_obj = self.name
        parts = []
        extras = name_obj.extra
        if extras:
            if extras.get('instrumental'):
                parts.append('Inst.')

            for key in ('version', 'edition'):
                if value := extras.get(key):
                    parts.append(value)

            if collabs:
                if feat := extras.get('feat'):
                    parts.append(f'feat. {feat}')
                if collab := extras.get('collabs'):
                    parts.append(f'with {collab}')

        if parts:
            parts = ' '.join(f'({part})' for part in parts)
            return f'{name_obj} {parts}'
        else:
            return str(name_obj)

    def format_path(self, fmt=PATH_FORMATS['alb_type_no_num'], ext='mp3'):
        album_part = self.album_part
        edition = album_part.edition
        artist_name = edition.artist.english if edition.artist else edition._artist.show
        if edition.edition:
            album_name = f'{edition.name} - {edition.edition}'
        else:
            album_name = str(edition.name)
        args = {
            'artist': artist_name,
            'album_type': edition.type.real_name,
            'date': edition.date.strftime('%Y.%m.%d'),
            'album': album_name,
            'album_num': None,
            'num': self.num,
            'track': self.name,
            'ext': ext
        }
        return fmt.format(**args)
