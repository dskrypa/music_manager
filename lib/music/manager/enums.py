"""
:author: Doug Skrypa
"""

import logging
from enum import Enum

__all__ = ['CollabMode']
log = logging.getLogger(__name__)


class CollabMode(Enum):
    ARTIST = 'artist'
    TITLE = 'title'
    BOTH = 'both'
