"""
:author: Doug Skrypa
"""

__all__ = ['MusicWikiException', 'EntityTypeError', 'NoPagesFoundError', 'BadLinkError', 'NoLinkTarget', 'NoLinkSite']


class MusicWikiException(Exception):
    """Base Music Manager Wiki exception class"""


class EntityTypeError(MusicWikiException, TypeError):
    """An incompatible WikiEntity type was provided"""


class NoPagesFoundError(MusicWikiException):
    """No pages could be found for a given title, on any site"""


class BadLinkError(MusicWikiException):
    """A link was missing a key field to be useful"""
    _problem = 'One or more key fields is missing'

    def __init__(self, link):
        self.link = link

    def __str__(self):
        return f'{self.__class__.__name__}: {self._problem} for link={self.link}'


class NoLinkTarget(BadLinkError):
    _problem = 'No link target title found'


class NoLinkSite(BadLinkError):
    _problem = 'No source site found'
