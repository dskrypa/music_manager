"""
:author: Doug Skrypa
"""

__all__ = ['MusicWikiException', 'EntityTypeError', 'NoPagesFoundError']


class MusicWikiException(Exception):
    """Base Music Manager Wiki exception class"""


class EntityTypeError(MusicWikiException, TypeError):
    """An incompatible WikiEntity type was provided"""


class NoPagesFoundError(MusicWikiException):
    """No pages could be found for a given title, on any site"""
