"""
:author: Doug Skrypa
"""

__all__ = ['PlexException', 'PlexQueryException', 'InvalidQueryFilter', 'InvalidPlaylist']


class PlexException(Exception):
    """Base exception for the Plex package"""


class PlexQueryException(PlexException):
    """Base query exception"""


class InvalidQueryFilter(PlexQueryException):
    """An invalid query filter was provided"""


class InvalidPlaylist(PlexException):
    """Exception to be raised when an operation is attempted on a playlist does not exist"""
