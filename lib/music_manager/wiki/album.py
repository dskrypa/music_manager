"""
:author: Doug Skrypa
"""

import logging

from .base import WikiEntity

__all__ = [
    'Discography', 'DiscographyEntry', 'AlbumPart', 'Album', 'AlbumVersion', 'Single', 'SoundtrackPart', 'Soundtrack'
]
log = logging.getLogger(__name__)


class Discography(WikiEntity):
    _categories = ('discography',)


class DiscographyEntry(WikiEntity):
    """Any item that would be in an artist's top-level discography."""
    _categories = ()

    def __init__(self, name, pages, album_type=None, language=None, discography_entry=None):
        """
        :param str name: The name of this discography entry
        :param WikiPage|dict|iterable pages: One or more WikiPage objects
        :param str album_type: The album type (Mini album, single, etc.)
        :param str language: The album language
        :param Node|str discography_entry:
        """
        super().__init__(name, pages)
        self.album_type = album_type
        self.language = language
        self.discography_entries = []
        if discography_entry:
            self.discography_entries.append(discography_entry)


class AlbumPart(WikiEntity):
    _categories = ()


class Album(DiscographyEntry):
    _categories = ('album',)


class AlbumVersion(DiscographyEntry):
    """A repackage or alternate edition of an album"""
    _categories = ()


class Single(DiscographyEntry):
    _categories = ('single',)


class SoundtrackPart(AlbumPart):
    """A part of a multi-part soundtrack"""
    _categories = ()


class Soundtrack(DiscographyEntry):
    _categories = ('ost', 'soundtrack')
