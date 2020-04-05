"""
:author: Doug Skrypa
"""

import logging

__all__ = ['NoArtistFoundException']
log = logging.getLogger(__name__)


class NoArtistFoundException(Exception):
    """Exception to be raised when no artist can be found for a given album"""
