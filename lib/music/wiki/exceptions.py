"""
:author: Doug Skrypa
"""

from typing import List as ListType

from wiki_nodes.nodes import List, Link
from wiki_nodes.page import WikiPage

__all__ = [
    'MusicWikiException', 'EntityTypeError', 'NoPagesFoundError', 'BadLinkError', 'NoLinkTarget', 'NoLinkSite',
    'AmbiguousPageError'
]


class MusicWikiException(Exception):
    """Base Music Manager Wiki exception class"""


class AmbiguousPageError(MusicWikiException):
    """The provided title/link pointed to a disambiguation page"""
    def __init__(self, name, obj):
        self.name = name
        self.obj = obj
        self.links = None
        if isinstance(obj, WikiPage):
            self.links = []             # type: ListType[Link]
            for section in obj:
                if isinstance(section.content, List):
                    for entry in section.content.iter_flat():
                        if isinstance(entry[0], Link):
                            self.links.append(entry[0])
                else:
                    for link_list in section.content.find_all(List):
                        for entry in link_list.iter_flat():
                            if isinstance(entry[0], Link):
                                self.links.append(entry[0])

    def __str__(self):
        if self.links:
            return '{} is a disambiguation page - links:\n - {}'.format(self.obj, '\n - '.join(map(str, self.links)))
        else:
            return f'The WikiEntity with name={self.name!r} obj={self.obj} is a disambiguation page'


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
