"""
Exceptions used during wiki parsing/processing.

:author: Doug Skrypa
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Mapping, Sequence, Collection

if TYPE_CHECKING:
    from wiki_nodes import WikiPage, Link

__all__ = [
    'MusicWikiException',
    'EntityTypeError',
    'NoPagesFoundError',
    'NoLinkedPagesFoundError',
    'AmbiguousWikiPageError',
    'AmbiguousPageError',
    'AmbiguousPagesError',
    'UnexpectedPageContent',
]


class MusicWikiException(Exception):
    """Base Music Manager Wiki exception class"""


# region Ambiguous Page/Link Exceptions


class AmbiguousWikiPageError(MusicWikiException):
    def __init__(self, name: str):
        self.name = name
        self._context = []

    def add_context(self, context: str):
        self._context.append(context)

    @property
    def context(self) -> str:
        return ''.join(f'[{entry}]' for entry in reversed(self._context))


class AmbiguousPageError(AmbiguousWikiPageError):
    """The provided title/link pointed to a disambiguation page"""
    def __init__(self, name: str, page: 'WikiPage', links: Sequence['Link'] = None):
        super().__init__(name)
        self.page = page
        self.links = links

    def __str__(self) -> str:
        context = f'{context} ' if (context := self.context) else ''
        base = f'{context}{self.page} is a disambiguation page'
        if self.links:
            return '{} - links:\n - {}'.format(base, '\n - '.join(map(str, self.links)))
        else:
            return f'{base}, but no links to valid candidates were found'


class AmbiguousPagesError(AmbiguousWikiPageError):
    def __init__(self, name, page_link_map: Mapping['WikiPage', Sequence['Link']]):
        super().__init__(name)
        self.page_link_map = page_link_map

    def __str__(self) -> str:
        parts = []
        for page, links in self.page_link_map.items():
            parts.append(f'{page}:')
            parts.append('\n - '.join(map(str, links)))
        parts = '\n'.join(parts)
        mid = 'Only disambiguation pages with no valid candidates could be found'
        context = f'{context} ' if (context := self.context) else ''
        return f'{context}{mid} for name={self.name!r}:\n{parts}'


# endregion


class EntityTypeError(MusicWikiException, TypeError):
    """An incompatible WikiEntity type was provided"""


class NoPagesFoundError(MusicWikiException):
    """No pages could be found for a given title, on any site"""


class NoLinkedPagesFoundError(MusicWikiException, ValueError):
    """No pages could be found from the given links"""

    def __init__(self, links: Collection[Link], source: str = None):
        self.links = links
        self.source = source

    def __str__(self) -> str:
        message = f'No pages were found from links={self.links}'
        if source := self.source:
            message += f' from source={source}'
        return message


class UnexpectedPageContent(MusicWikiException):
    """The content on a page did not match what it was expected to contain."""
