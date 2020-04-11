"""
:author: Doug Skrypa
"""

from typing import Optional, List

from wiki_nodes import WikiPage, Link

__all__ = [
    'MusicWikiException', 'EntityTypeError', 'NoPagesFoundError', 'BadLinkError', 'NoLinkTarget', 'NoLinkSite',
    'AmbiguousPageError'
]


class MusicWikiException(Exception):
    """Base Music Manager Wiki exception class"""


class AmbiguousPageError(MusicWikiException):
    """The provided title/link pointed to a disambiguation page"""
    def __init__(self, name: str, page: WikiPage, links: Optional[List[Link]] = None):
        self.name = name
        self.page = page
        self.links = links

    def __str__(self):
        if self.links:
            return '{} is a disambiguation page - links:\n - {}'.format(self.page, '\n - '.join(map(str, self.links)))
        else:
            return f'{self.page} is a disambiguation page, but no links to valid candidates were found'


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
