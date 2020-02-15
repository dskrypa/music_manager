"""
:author: Doug Skrypa
"""

import logging
import re
from datetime import datetime
from traceback import format_stack

from ds_tools.caching import ClearableCachedPropertyMixin
from ds_tools.compat import cached_property
from .base import WikiEntity
from .exceptions import EntityTypeError

__all__ = ['DiscographyEntry', 'AlbumPart', 'Album', 'AlbumVersion', 'Single', 'SoundtrackPart', 'Soundtrack']
log = logging.getLogger(__name__)
OST_PAT = re.compile(r'^(.*? OST) (PART.?\s?\d+)$')


class DiscographyEntry(WikiEntity, ClearableCachedPropertyMixin):
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
        if name and name.startswith('"') and name.endswith('"'):
            name = name[1:-1]
        super().__init__(name, pages)
        self.disco_entries = [disco_entry] if disco_entry else []
        self._date = None

    def __repr__(self):
        return f'<{type(self).__name__}[{self.date_str}]({self.name!r})[pages: {len(self._pages)}]>'

    def __lt__(self, other):
        return self._sort_key < other._sort_key

    @cached_property
    def _sort_key(self):
        date = self.date or datetime.fromtimestamp(0)
        return self.year or date.year, date, self.name or ''

    @cached_property
    def _merge_key(self):
        uc_name = self.name.upper()
        ost_match = OST_PAT.match(uc_name)
        if ost_match:
            uc_name = ost_match.group(1)
        return self.year, uc_name

    @cached_property
    def year(self):
        for entry in self.disco_entries:
            if entry.date:
                return entry.date.year
            elif entry.year:
                return entry.year
        return None

    @cached_property
    def date_str(self):
        return self.date.strftime('%Y-%m-%d') if self.date else str(self.year)

    @cached_property
    def date(self):
        if not isinstance(self._date, datetime):
            for entry in self.disco_entries:
                if entry.date:
                    self._date = entry.date
                    break
        return self._date

    def _merge(self, other):
        self._pages.update(other._pages)
        self.disco_entries.extend(other.disco_entries)
        self.clear_cached_properties()

    @classmethod
    def from_disco_entry(cls, disco_entry):
        categories = disco_entry.categories
        # log.debug(f'Creating {cls.__name__} from {disco_entry} with categories={categories}')
        try:
            return cls._by_category(disco_entry.title, disco_entry, categories, disco_entry=disco_entry)
        except EntityTypeError as e:
            log.error(f'Failed to create {cls.__name__} from {disco_entry}: {"".join(format_stack())}\n{e}', extra={'color': 'red'})


class AlbumPart(WikiEntity):
    _categories = ()


class Album(DiscographyEntry):
    """An album or mini album or EP"""
    _categories = ('album', 'extended play', '(band) eps', '-language eps')


class AlbumVersion(DiscographyEntry):
    """A repackage or alternate edition of an album"""
    _categories = ()


class Single(DiscographyEntry):
    _categories = ('single', 'song', 'collaboration', 'feature')
    _not_categories = ('songwriter',)


class SoundtrackPart(AlbumPart):
    """A part of a multi-part soundtrack"""
    _categories = ()


class Soundtrack(DiscographyEntry):
    _categories = ('ost', 'soundtrack')
