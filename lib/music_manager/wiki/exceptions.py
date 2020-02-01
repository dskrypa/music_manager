"""
:author: Doug Skrypa
"""

__all__ = ['MusicWikiException', 'EntityTypeError']

class MusicWikiException(Exception):
    """Base Music Manager Wiki exception class"""


class EntityTypeError(MusicWikiException, TypeError):
    """An incompatible WikiEntity type was provided"""
