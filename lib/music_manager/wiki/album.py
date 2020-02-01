"""
:author: Doug Skrypa
"""

import logging

from .base import WikiEntity

__all__ = ['Discography', 'SongCollection', 'SongCollectionPart', 'Album', 'Single', 'Soundtrack']
log = logging.getLogger(__name__)


class Discography(WikiEntity):
    _categories = ('discography',)


class SongCollection(WikiEntity):
    _categories = ()


class SongCollectionPart(WikiEntity):
    _categories = ()


class Album(SongCollection):
    _categories = ('album',)


class Single(SongCollection):
    _categories = ('single',)


class Soundtrack(SongCollection):
    _categories = ('ost', 'soundtrack')
