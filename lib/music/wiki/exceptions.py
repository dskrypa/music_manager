"""
:author: Doug Skrypa
"""

from typing import Optional, Mapping, Sequence

from wiki_nodes import WikiPage, Link

__all__ = [
    'MusicWikiException',
    'EntityTypeError',
    'NoPagesFoundError',
    'BadLinkError',
    'NoLinkTarget',
    'NoLinkSite',
    'AmbiguousWikiPageError',
    'AmbiguousPageError',
    'AmbiguousPagesError',
    'SiteDoesNotExist',
]


class MusicWikiException(Exception):
    """Base Music Manager Wiki exception class"""


class AmbiguousWikiPageError(MusicWikiException):
    def __init__(self, name: str):
        self.name = name
        self._context = []

    def add_context(self, context: str):
        self._context.append(context)

    @property
    def context(self):
        return ''.join(f'[{entry}]' for entry in reversed(self._context))


class AmbiguousPageError(AmbiguousWikiPageError):
    """The provided title/link pointed to a disambiguation page"""
    def __init__(self, name: str, page: WikiPage, links: Optional[Sequence[Link]] = None):
        super().__init__(name)
        self.page = page
        self.links = links

    def __str__(self):
        context = f'{context} ' if (context := self.context) else ''
        base = f'{context}{self.page} is a disambiguation page'
        if self.links:
            return '{} - links:\n - {}'.format(base, '\n - '.join(map(str, self.links)))
        else:
            return f'{base}, but no links to valid candidates were found'


class AmbiguousPagesError(AmbiguousWikiPageError):
    def __init__(self, name, page_link_map: Mapping[WikiPage, Sequence[Link]]):
        super().__init__(name)
        self.page_link_map = page_link_map

    def __str__(self):
        parts = []
        for page, links in self.page_link_map.items():
            parts.append(f'{page}:')
            parts.append('\n - '.join(map(str, links)))
        parts = '\n'.join(parts)
        mid = 'Only disambiguation pages with no valid candidates could be found'
        context = f'{context} ' if (context := self.context) else ''
        return f'{context}{mid} for name={self.name!r}:\n{parts}'


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


class SiteDoesNotExist(BadLinkError):
    _problem = 'Site does not exist'
