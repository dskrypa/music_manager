"""
:author: Doug Skrypa
"""

import logging
import re
from datetime import datetime
from traceback import format_stack

from ds_tools.caching import ClearableCachedPropertyMixin
from ds_tools.compat import cached_property
from wiki_nodes.http import MediaWikiClient
from wiki_nodes.nodes import MappingNode, String, CompoundNode
from wiki_nodes.utils import strip_style
from .base import WikiEntity
from .exceptions import EntityTypeError

__all__ = [
    'DiscographyEntry', 'Album', 'Single', 'SoundtrackPart', 'Soundtrack', 'DiscographyEntryEdition',
    'DiscographyEntryPart'
]
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

    @cached_property
    def editions(self):
        # one or more DiscographyEntryEdition values
        editions = []
        for site, entry_page in self._pages.items():
            if site == 'www.generasia.com':
                processed = entry_page.sections.processed()
                for node in processed:
                    if isinstance(node, MappingNode):
                        artist_link = node['Artist'].value
                        album_name = node['Album'].value.value
                        release_dates = node['Released']
                        if release_dates.children:
                            _dates = []
                            for r_date in release_dates.iter_flat():
                                if isinstance(r_date, String):
                                    _dates.append(datetime.strptime(r_date.value, '%Y.%m.%d'))
                                else:
                                    _dates.append(datetime.strptime(r_date[0].value, '%Y.%m.%d'))
                            release_dates = _dates
                        else:
                            release_dates = [datetime.strptime(release_dates.value.value, '%Y.%m.%d')]

                        for key, value in node.items():
                            lc_key = key.lower().strip()
                            if 'tracklist' in lc_key:
                                if lc_key != 'tracklist':
                                    edition = strip_style(key.rsplit(maxsplit=1)[0]).strip('"')
                                else:
                                    edition = None
                                editions.append(DiscographyEntryEdition(
                                    album_name, entry_page, artist_link, release_dates, value, edition
                                ))
            elif site == 'wiki.d-addicts.com':
                pass
            elif site == 'kpop.fandom.com':
                pass
            elif site == 'en.wikipedia.org':
                pass
            else:
                log.debug(f'No discography entry extraction is configured for {entry_page}')

        return editions


class Album(DiscographyEntry):
    """An album or mini album or EP, or a repackage thereof"""
    _categories = ('album', 'extended play', '(band) eps', '-language eps')


class Single(DiscographyEntry):
    _categories = ('single', 'song', 'collaboration', 'feature')
    _not_categories = ('songwriter',)


class Soundtrack(DiscographyEntry):
    _categories = ('ost', 'soundtrack')


class DiscographyEntryEdition:
    """An edition of an album"""
    def __init__(self, name, page, artist, release_dates, tracks, edition=None):
        self.name = name
        self.page = page
        self.artist = artist
        self.release_dates = release_dates
        self.tracks = tracks
        self.edition = edition

    def __repr__(self):
        date = self.release_dates[0].strftime('%Y-%m-%d')
        edition = f'[edition={self.edition!r}]' if self.edition else ''
        return f'<{self.__class__.__name__}[{date}][{self.name!r} @ {self.page}]{edition}>'

    @cached_property
    def parts(self):
        # One or more DiscographyEntryPart values
        # Example with multiple parts (disks): https://www.generasia.com/wiki/Love_Yourself_Gyeol_%27Answer%27
        return []


class DiscographyEntryPart:
    def __init__(self):
        pass


class SoundtrackPart(DiscographyEntryPart):
    """A part of a multi-part soundtrack"""
    pass
