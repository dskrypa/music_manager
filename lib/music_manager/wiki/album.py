"""
:author: Doug Skrypa
"""

import logging

from .base import WikiEntity

__all__ = ['DiscographyEntry', 'AlbumPart', 'Album', 'AlbumVersion', 'Single', 'SoundtrackPart', 'Soundtrack']
log = logging.getLogger(__name__)


class DiscographyEntry(WikiEntity):
    """
    A page or set of pages for any item in an artist's top-level discography, i.e., albums, soundtracks, singles,
    collaborations.

    Individiual tracks are represented by :class:`Track<.track.Track>` objects.
    """
    _categories = ()

    def __init__(self, name=None, pages=None, disco_entry=None):
        """
        :param str name: The name of this discography entry
        :param WikiPage|dict|iterable pages: One or more WikiPage objects
        :param DiscoEntry disco_entry: The :class:`DiscoEntry<.shared.DiscoEntry>` containing the Node and metadata from
          the artist or Discography page about this entry.
        """
        super().__init__(name, pages)
        self.disco_entries = []
        if disco_entry:
            self.disco_entries.append(disco_entry)

    @classmethod
    def from_disco_entry(cls, disco_entry):
        link = disco_entry.link
        name = disco_entry.title if disco_entry.title else (link.text or link.title) if link else None
        categories = disco_entry.type.value[1] if disco_entry.type else []
        return cls._by_category(name, disco_entry, categories, disco_entry=disco_entry)


class AlbumPart(WikiEntity):
    _categories = ()


class Album(DiscographyEntry):
    """An album or mini album or EP"""
    _categories = ('album', 'extended play')


class AlbumVersion(DiscographyEntry):
    """A repackage or alternate edition of an album"""
    _categories = ()


class Single(DiscographyEntry):
    _categories = ('single', 'song')
    _not_categories = ('songwriter',)


class SoundtrackPart(AlbumPart):
    """A part of a multi-part soundtrack"""
    _categories = ()


class Soundtrack(DiscographyEntry):
    _categories = ('ost', 'soundtrack')
