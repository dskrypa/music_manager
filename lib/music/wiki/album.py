"""
:author: Doug Skrypa
"""

import logging
import re
from datetime import datetime, date
from traceback import format_stack
from typing import TYPE_CHECKING, List, Optional, Tuple, Sequence, Iterator

from ds_tools.caching import ClearableCachedPropertyMixin
from ds_tools.compat import cached_property
from wiki_nodes.nodes import Node, Link, List as ListNode
from wiki_nodes.page import WikiPage
from ..text.name import Name
from .base import WikiEntity, Pages
from .exceptions import EntityTypeError, BadLinkError

if TYPE_CHECKING:
    from .disco_entry import DiscoEntry, DiscoEntryType

__all__ = [
    'DiscographyEntry', 'Album', 'Single', 'SoundtrackPart', 'Soundtrack', 'DiscographyEntryEdition',
    'DiscographyEntryPart'
]
log = logging.getLogger(__name__)
OST_MATCH = re.compile(r'^(.*? OST) (PART.?\s?\d+)$').match


class DiscographyEntry(WikiEntity, ClearableCachedPropertyMixin):
    """
    A page or set of pages for any item in an artist's top-level discography, i.e., albums, soundtracks, singles,
    collaborations.

    Individiual tracks are represented by :class:`Track<.track.Track>` objects.
    """
    _categories = ()

    def __init__(self, name: Optional[str] = None, pages: Pages = None, disco_entry: Optional['DiscoEntry'] = None):
        """
        :param str name: The name of this discography entry
        :param WikiPage|dict|iterable pages: One or more WikiPage objects
        :param DiscoEntry disco_entry: The :class:`DiscoEntry<.disco_entry.DiscoEntry>` containing the Node and metadata
          from the artist or Discography page about this entry.
        """
        if name and name.startswith('"') and name.endswith('"'):
            name = name[1:-1]
        super().__init__(name, pages)
        self.disco_entries = [disco_entry] if disco_entry else []   # type: List[DiscoEntry]
        self._date = None                                           # type: Optional[date]

    @cached_property
    def name(self) -> Name:
        # TODO: Provide full name
        return Name(self._name)

    def __repr__(self):
        return f'<[{self.date_str}]{self.__class__.__name__}({self._name!r})[pages: {len(self._pages)}]>'

    def __lt__(self, other: 'DiscographyEntry'):
        return self._sort_key < other._sort_key

    def __iter__(self) -> Iterator['DiscographyEntryEdition']:
        """Iterate over every edition part in this DiscographyEntry"""
        for edition in self.editions:
            yield from edition

    @cached_property
    def _sort_key(self) -> Tuple[int, date, str]:
        date = self.date or datetime.fromtimestamp(0).date()
        return self.year or date.year, date, self.name or ''

    @cached_property
    def _merge_key(self) -> Tuple[Optional[int], str]:
        uc_name = self._name.upper()
        if ost_match := OST_MATCH(uc_name):
            uc_name = ost_match.group(1)
        return self.year, uc_name

    @cached_property
    def year(self) -> Optional[int]:
        for entry in self.disco_entries:
            if entry.date:
                return entry.date.year
            elif entry.year:
                return entry.year
        return None

    @cached_property
    def date_str(self) -> str:
        return self.date.strftime('%Y-%m-%d') if self.date else str(self.year)

    @cached_property
    def date(self) -> Optional[date]:
        if not isinstance(self._date, date):
            for entry in self.disco_entries:
                if entry.date:
                    self._date = entry.date
                    break
        return self._date

    def _merge(self, other: 'DiscographyEntry'):
        self._pages.update(other._pages)
        self.disco_entries.extend(other.disco_entries)
        self.clear_cached_properties()

    @classmethod
    def from_disco_entry(cls, disco_entry: 'DiscoEntry') -> 'DiscographyEntry':
        categories = disco_entry.categories
        # log.debug(f'Creating {cls.__name__} from {disco_entry} with categories={categories}')
        try:
            return cls._by_category(disco_entry.title, disco_entry, categories, disco_entry=disco_entry)
        except EntityTypeError as e:
            err_msg = f'Failed to create {cls.__name__} from {disco_entry}: {"".join(format_stack())}\n{e}'
            log.error(err_msg, extra={'color': 'red'})

    @cached_property
    def editions(self) -> List['DiscographyEntryEdition']:
        editions = []
        for site, entry_page in self._pages.items():
            try:
                parser = WikiParser.for_site(site)
            except KeyError:
                log.debug(f'No discography entry extraction is configured for {entry_page}')
            else:
                editions.extend(parser.process_album_editions(self, entry_page))
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
    def __init__(
            self, name: Optional[str], page: WikiPage, artist: Optional[Node], release_dates: Sequence[date],
            tracks: ListNode, entry_type: 'DiscoEntryType', edition: Optional[str] = None, lang: Optional[str] = None
    ):
        self.name = name                        # type: Optional[str]
        self.page = page                        # type: WikiPage
        self.release_dates = release_dates      # type: Sequence[date]
        self._tracks = tracks                   # type: ListNode
        self.type = entry_type                  # type: DiscoEntryType
        self.edition = edition                  # type: Optional[str]
        self._artist = artist                   # type: Optional[Node]
        self.lang = lang                        # type: Optional[str]
        # TODO: 1st/2nd/3rd/etc (Mini) Album...

    def __repr__(self) -> str:
        date = self.release_dates[0].strftime('%Y-%m-%d')
        edition = f'[edition={self.edition!r}]' if self.edition else ''
        lang = f'[lang={self.lang!r}]' if self.lang else ''
        return f'<[{date}]{self.__class__.__name__}[{self.name!r} @ {self.page}]{edition}{lang}>'

    def __iter__(self) -> Iterator['DiscographyEntryPart']:
        return iter(self.parts)

    def __lt__(self, other: 'DiscographyEntryEdition') -> bool:
        return (self.artist, self.date, self.name, self.edition) < (other.artist, other.date, other.name, other.edition)

    @cached_property
    def artist(self) -> Optional['Artist']:
        if isinstance(self._artist, Link):
            try:
                return Artist.from_link(self._artist)
            except BadLinkError as e:
                log.debug(f'Error getting artist={self._artist} for {self}: {e}')
        return None

    @cached_property
    def date(self) -> date:
        return min(self.release_dates)

    @cached_property
    def parts(self) -> List['DiscographyEntryPart']:
        # Example with multiple parts (disks): https://www.generasia.com/wiki/Love_Yourself_Gyeol_%27Answer%27
        parts = []
        site = self.page.site
        if site == 'www.generasia.com':
            if self._tracks[0].children:
                for node in self._tracks:
                    parts.append(DiscographyEntryPart(node.value.value, self, node.sub_list))
            else:
                parts.append(DiscographyEntryPart(None, self, self._tracks))
        elif site == 'wiki.d-addicts.com':
            pass
        elif site == 'kpop.fandom.com':
            pass
        elif site == 'en.wikipedia.org':
            pass
        else:
            log.debug(f'No discography entry part extraction is configured for {self.page}')
        return parts


class DiscographyEntryPart:
    _disc_match = re.compile('(?:DVD|CD|Dis[ck])\s*(\d+)', re.IGNORECASE).match

    def __init__(self, name: Optional[str], edition: DiscographyEntryEdition, tracks: ListNode):
        self.name = name                                # type: Optional[str]
        self.edition = edition                          # type: DiscographyEntryEdition
        self._tracks = tracks                           # type: ListNode
        m = self._disc_match(name) if name else None
        self.disc = int(m.group(1)) if m else 1         # type: int

    def __repr__(self) -> str:
        ed = self.edition
        date = ed.release_dates[0].strftime('%Y-%m-%d')
        edition = f'[edition={ed.edition!r}]' if ed.edition else ''
        name = f'[{self.name}]' if self.name else ''
        return f'<[{date}]{self.__class__.__name__}[{ed.name!r} @ {ed.page}]{edition}{name}>'

    def __lt__(self, other: 'DiscographyEntryPart') -> bool:
        return (self.edition, self.name) < (other.edition, other.name)

    def __iter__(self) -> Iterator['Track']:
        return iter(self.tracks)

    @cached_property
    def track_names(self) -> List[Name]:
        try:
            parse_track_name = WikiParser.for_site(self.edition.page.site).parse_track_name
        except KeyError:
            log.debug(f'No track name extraction is configured for {self.edition.page}')
            return []
        else:
            return [parse_track_name(node) for node in self._tracks.iter_flat()]

    @cached_property
    def tracks(self) -> List['Track']:
        return [Track(i + 1, name, self) for i, name in enumerate(self.track_names)]


class SoundtrackPart(DiscographyEntryPart):
    """A part of a multi-part soundtrack"""
    pass


# Down here due to circular dependency
from .artist import Artist
from .parsing import WikiParser
from .track import Track
