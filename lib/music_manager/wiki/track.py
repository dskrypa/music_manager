"""
:author: Doug Skrypa
"""

import logging

__all__ = ['Track']
log = logging.getLogger(__name__)


class Track:
    def __init__(self, num, name, album_part):
        self.num = num
        self.name = name
        self.album_part = album_part

    def __repr__(self):
        return f'<{self.__class__.__name__}[{self.num:02d}: {self.name!r} @ {self.album_part}]>'

    def __lt__(self, other):
        return (self.album_part, self.num, self.name) < (other.album_part, other.num, other.name)
