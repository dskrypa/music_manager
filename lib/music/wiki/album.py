"""
:author: Doug Skrypa
"""

import logging
import re
from datetime import datetime, date
from traceback import format_stack
from typing import List, Optional, Tuple, Sequence, Iterator, MutableSet, Set, Union, Iterable

from ordered_set import OrderedSet

from ds_tools.caching import ClearableCachedPropertyMixin
from ds_tools.compat import cached_property
from ds_tools.utils.misc import num_suffix
from wiki_nodes import WikiPage, Node, Link, List as ListNode
from ..common import DiscoEntryType
from ..text import combine_with_parens, Name
from .base import EntertainmentEntity, Pages
from .disco_entry import DiscoEntry
from .exceptions import EntityTypeError, BadLinkError

__all__ = [
    'DiscographyEntry', 'Album', 'Single', 'SoundtrackPart', 'Soundtrack', 'DiscographyEntryEdition',
    'DiscographyEntryPart'
]
log = logging.getLogger(__name__)
OST_MATCH = re.compile(r'^(.*? OST) (PART.?\s?\d+)$').match


class DiscographyEntry(EntertainmentEntity, ClearableCachedPropertyMixin):
    """
    A page or set of pages for any item in an artist's top-level discography, i.e., albums, soundtracks, singles,
    collaborations.

    Individiual tracks are represented by :class:`Track<.track.Track>` objects.
    """
    _categories = ()

    def __init__(
            self, name: Optional[str] = None, pages: Pages = None, disco_entry: Optional['DiscoEntry'] = None,
            artist: Optional['Artist'] = None, entry_type: Optional['DiscoEntryType'] = None
    ):
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
        self._artist = artist                                       # type: Optional[Artist]
        self._type = entry_type                                     # type: Optional[DiscoEntryType]

    @cached_property
    def name(self) -> Name:
        if names := self.names:
            return next(iter(names))
        return Name(self._name)

    @cached_property
    def names(self) -> MutableSet[Name]:
        names = OrderedSet()
        for edition in self.editions:
            names.add(Name(edition._name))
        return names

    @cached_property
    def names_str(self):
        names = self.names or [self.name]
        return ' / '.join(map(str, names))

    def __repr__(self):
        return f'<[{self.date_str}]{self.cls_type_name}({self.names_str!r})[pages: {len(self._pages)}]>'

    def __lt__(self, other: 'DiscographyEntry'):
        return self._sort_key < other._sort_key

    def __iter__(self) -> Iterator['DiscographyEntryEdition']:
        """Iterate over every edition part in this DiscographyEntry"""
        return iter(self.editions)

    def __bool__(self):
        return bool(self.editions)

    @cached_property
    def artist(self) -> Optional['Artist']:
        if isinstance(self._artist, Artist):
            return self._artist
        for edition in self.editions:
            if edition.artist:
                return edition.artist
        return None

    @cached_property
    def type(self) -> Optional['DiscoEntryType']:
        if isinstance(self._type, DiscoEntryType):
            return self._type
        for edition in self.editions:
            if edition.type:
                return edition.type
        return None

    @cached_property
    def cls_type_name(self):
        return self.type.name if self.type else self.__class__.__name__

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
            else:
                self._date = min(edition.date for edition in self.editions) if self.editions else None
        return self._date

    def _merge(self, other: 'DiscographyEntry'):
        self._pages.update(other._pages)
        self.disco_entries.extend(other.disco_entries)
        self.clear_cached_properties()

    @classmethod
    def from_disco_entry(cls, disco_entry: 'DiscoEntry') -> 'DiscographyEntry':
        # log.debug(f'Creating {cls.__name__} from {disco_entry} with categories={categories}')
        try:
            return cls._by_category(disco_entry, disco_entry=disco_entry)
        except EntityTypeError as e:
            err_msg = f'Failed to create {cls.__name__} from {disco_entry}: {"".join(format_stack())}\n{e}'
            log.error(err_msg, extra={'color': 'red'})

    @cached_property
    def editions(self) -> List['DiscographyEntryEdition']:
        editions = []
        for entry_page, parser in self.page_parsers('process_album_editions'):
            editions.extend(parser.process_album_editions(self, entry_page))
        return editions

    def parts(self) -> Iterator['DiscographyEntryPart']:
        for edition in self.editions:
            yield from edition

    @cached_property
    def number(self) -> Optional[int]:
        for page, parser in self.page_parsers('parse_album_number'):
            return parser.parse_album_number(page)
        return None


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
            self, name: Optional[str], page: WikiPage, entry: DiscographyEntry, entry_type: 'DiscoEntryType',
            artist: Union[Node, Iterable[Node], None], release_dates: Sequence[date], tracks: ListNode,
            edition: Optional[str] = None, lang: Optional[str] = None, repackage=False
    ):
        self._name = name                       # type: Optional[str]
        self.page = page                        # type: WikiPage
        self.entry = entry                      # type: DiscographyEntry
        self.type = entry_type                  # type: DiscoEntryType
        self._artist = artist                   # type: Union[Node, Iterable[Node], None]
        self.release_dates = release_dates      # type: Sequence[date]
        self._tracks = tracks                   # type: ListNode
        self.edition = edition                  # type: Optional[str]
        self.lang = lang                        # type: Optional[str]
        self.repackage = repackage

    def __repr__(self) -> str:
        _date = self.release_dates[0].strftime('%Y-%m-%d')
        _type = self.numbered_type or (repr(self.type.real_name) if self.type else None)
        alb_type = f'[type={_type}]' if _type else ''
        edition = f'[edition={self.edition!r}]' if self.edition else ''
        lang = f'[lang={self.lang!r}]' if self.lang else ''
        return f'<[{_date}]{self.cls_type_name}[{self._name!r} @ {self.page}]{alb_type}{edition}{lang}>'

    def __iter__(self) -> Iterator['DiscographyEntryPart']:
        return iter(self.parts)

    def __bool__(self):
        return bool(self.parts)

    def __lt__(self, other: 'DiscographyEntryEdition') -> bool:
        return (self.artist, self.date, self._name, self.edition) < (other.artist, other.date, other._name, other.edition)

    @cached_property
    def name(self):
        return Name(self.full_name())

    def full_name(self, hide_edition=False):
        parts = (self._name, self.edition if not hide_edition else None)
        return combine_with_parens(tuple(filter(None, parts)))

    @cached_property
    def cls_type_name(self):
        return self.entry.cls_type_name + 'Edition'

    @cached_property
    def artists(self) -> Optional[Set['Artist']]:
        return None

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

    @cached_property
    def numbered_type(self) -> Optional[str]:
        if (num := self.entry.number) and self.type:
            parts = (
                f'{num}{num_suffix(num)}',
                # TODO: Determine artist's primary lang, include only if it doesn't match
                self.lang if self.lang != 'Korean' else None,
                self.type.real_name, 'Repackage' if self.repackage else None
            )
            return ' '.join(filter(None, parts))
        return None


class DiscographyEntryPart:
    _disc_match = re.compile('(?:DVD|CD|Dis[ck])\s*(\d+)', re.IGNORECASE).match

    def __init__(self, name: Optional[str], edition: DiscographyEntryEdition, tracks: ListNode):
        self._name = name                               # type: Optional[str]
        self.edition = edition                          # type: DiscographyEntryEdition
        self._tracks = tracks                           # type: ListNode
        m = self._disc_match(name) if name else None
        self.disc = int(m.group(1)) if m else 1         # type: int

    def __repr__(self) -> str:
        ed = self.edition
        date = ed.release_dates[0].strftime('%Y-%m-%d')
        edition = f'[edition={ed.edition!r}]' if ed.edition else ''
        name = f'[{self._name}]' if self._name else ''
        return f'<[{date}]{self.cls_type_name}[{ed._name!r} @ {ed.page}]{edition}{name}>'

    def __lt__(self, other: 'DiscographyEntryPart') -> bool:
        return (self.edition, self._name) < (other.edition, other._name)

    def __iter__(self) -> Iterator['Track']:
        return iter(self.tracks)

    def __bool__(self):
        return bool(self.tracks)

    @cached_property
    def name(self):
        return Name(self.full_name())

    @cached_property
    def cls_type_name(self):
        return self.edition.entry.cls_type_name + 'Part'

    def full_name(self, hide_edition=False):
        edition = self.edition
        parts = (edition._name, self._name, edition.edition if not hide_edition else None)
        return combine_with_parens(tuple(filter(None, parts)))

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
