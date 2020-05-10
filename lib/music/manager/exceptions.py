"""
:author: Doug Skrypa
"""

import logging

__all__ = ['NoArtistFoundException', 'MatchException']
log = logging.getLogger(__name__)


class NoArtistFoundException(Exception):
    """Exception to be raised when no artist can be found for a given album"""


class MatchException(Exception):
    """Exception to be raised when a match cannot be found"""
    def __init__(self, lvl, msg):
        super().__init__(msg)
        self.lvl = lvl
