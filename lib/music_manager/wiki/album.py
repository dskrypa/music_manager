"""
:author: Doug Skrypa
"""

import logging

from .base import WikiEntity

__all__ = [
    'Discography', 'SongCollection', 'SongCollectionPart', 'Album', 'AlbumVersion', 'Single', 'SoundtrackPart',
    'Soundtrack'
]
log = logging.getLogger(__name__)


class Discography(WikiEntity):
    _categories = ('discography',)


class SongCollection(WikiEntity):
    _categories = ()


class SongCollectionPart(WikiEntity):
    _categories = ()


class Album(SongCollection):
    _categories = ('album',)


class AlbumVersion(SongCollection):
    """A repackage or alternate edition of an album"""
    _categories = ()


class Single(SongCollection):
    _categories = ('single',)


class SoundtrackPart(SongCollectionPart):
    """A part of a multi-part soundtrack"""
    _categories = ()


class Soundtrack(SongCollection):
    _categories = ('ost', 'soundtrack')
