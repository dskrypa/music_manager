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

    def from_disco_entry(self, disco_entry):
        # TODO: Pick class based on album type; set name
        pass


class AlbumPart(WikiEntity):
    _categories = ()


class Album(DiscographyEntry):
    """An album or mini album or EP"""
    _categories = ('album', 'ep', 'extended play')


class AlbumVersion(DiscographyEntry):
    """A repackage or alternate edition of an album"""
    _categories = ()


class Single(DiscographyEntry):
    _categories = ('single', 'song')


class SoundtrackPart(AlbumPart):
    """A part of a multi-part soundtrack"""
    _categories = ()


class Soundtrack(DiscographyEntry):
    _categories = ('ost', 'soundtrack')
