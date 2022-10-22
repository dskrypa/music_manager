"""
:author: Doug Skrypa
"""

from enum import Enum

__all__ = ['CollabMode']


class CollabMode(Enum):
    ARTIST = 'artist'
    TITLE = 'title'
    BOTH = 'both'

    @classmethod
    def get(cls, mode):
        return mode if isinstance(mode, cls) else cls(mode)
