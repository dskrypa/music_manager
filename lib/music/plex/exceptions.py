"""
:author: Doug Skrypa
"""

__all__ = ['PlexQueryException', 'InvalidQueryFilter']


class PlexQueryException(Exception):
    """Base query exception"""


class InvalidQueryFilter(PlexQueryException):
    """An invalid query filter was provided"""
