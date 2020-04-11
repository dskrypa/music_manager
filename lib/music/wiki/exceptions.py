"""
:author: Doug Skrypa
"""

from typing import Optional, Mapping, Sequence

from wiki_nodes import WikiPage, Link

__all__ = [
    'MusicWikiException', 'EntityTypeError', 'NoPagesFoundError', 'BadLinkError', 'NoLinkTarget', 'NoLinkSite',
    'AmbiguousPageError', 'AmbiguousPagesError'
]


class MusicWikiException(Exception):
    """Base Music Manager Wiki exception class"""


class AmbiguousPageError(MusicWikiException):
    """The provided title/link pointed to a disambiguation page"""
    def __init__(self, name: str, page: WikiPage, links: Optional[Sequence[Link]] = None):
        self.name = name
        self.page = page
        self.links = links

    def __str__(self):
        if self.links:
            return '{} is a disambiguation page - links:\n - {}'.format(self.page, '\n - '.join(map(str, self.links)))
        else:
            return f'{self.page} is a disambiguation page, but no links to valid candidates were found'


class AmbiguousPagesError(MusicWikiException):
    def __init__(self, name, page_link_map: Mapping[WikiPage, Sequence[Link]]):
        self.name = name
        self.page_link_map = page_link_map

    def __str__(self):
        parts = []
        for page, links in self.page_link_map.items():
            parts.append(f'{page}:')
            parts.append('\n - '.join(map(str, links)))
        parts = '\n'.join(parts)
        return f'Only disambiguation pages with no valid candidates could be found for name={self.name!r}:\n{parts}'


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
