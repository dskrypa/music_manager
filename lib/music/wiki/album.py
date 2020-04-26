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
from .parsing import WikiParser

__all__ = [
    'DiscographyEntry', 'Album', 'Single', 'SoundtrackPart', 'Soundtrack', 'DiscographyEntryEdition',
    'DiscographyEntryPart'
]
log = logging.getLogger(__name__)
OST_MATCH = re.compile(r'^(.*? OST) (PART.?\s?\d+)$').match
NodeOrNodes = Union[Node, Iterable[Node], None]
ListOrLists = Union[ListNode, Iterable[ListNode], None]


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
            names.add(edition.name_base)
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
    def artists(self) -> Set['Artist']:
        artists = set()
        if isinstance(self._artist, Artist):
            artists.add(self._artist)
        for edition in self.editions:
            artists.update(edition.artists)
        return artists

    @cached_property
    def artist(self) -> Optional['Artist']:
        if isinstance(self._artist, Artist):
            return self._artist
        elif artists := self.artists:
            if len(artists) == 1:
                return next(iter(artists))
            else:
                log.debug(f'Multiple artists found for {self!r}: {artists}')
        else:
            log.debug(f'No artists found for {self!r}')
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
    def _sort_key(self) -> Tuple[int, date, Name]:
        date = self.date or datetime.fromtimestamp(0).date()
        return self.year or date.year, date, self.name

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
            self, name: Union[str, Name, None], page: WikiPage, entry: DiscographyEntry, entry_type: 'DiscoEntryType',
            artist: NodeOrNodes, release_dates: Sequence[date], tracks: ListOrLists, edition: Optional[str] = None,
            lang: Optional[str] = None, repackage=False
    ):
        self._name = name                                                               # type: Union[str, Name, None]
        self.page = page                                                                # type: WikiPage
        self.entry = entry                                                              # type: DiscographyEntry
        self.type = entry_type                                                          # type: DiscoEntryType
        self._artist = artist                                                           # type: NodeOrNodes
        self.release_dates = release_dates                                              # type: Sequence[date]
        self._tracks = tracks                                                           # type: ListOrLists
        self.edition = edition                                                          # type: Optional[str]
        self.lang = 'Korean' if not lang and page.site == 'kpop.fandom.com' else lang   # type: Optional[str]
        self.repackage = repackage
        # TODO: Fix edition values here:
        """
            - <[2013-06-03]AlbumEdition['XOXO' @ <WikiPage['XOXO (EXO)' @ www.generasia.com]>][type=1st Chinese Album][edition='Kiss Edition - Hug Edition'][lang='Chinese']>:
            Artist: <Group('EXO (also called EXO Planet)')[pages: 1]>
            Parts:
              - <[2013-06-03]AlbumPart['XOXO' @ <WikiPage['XOXO (EXO)' @ www.generasia.com]>][edition='Kiss Edition - Hug Edition']>:
        """

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
    def name_base(self) -> Name:
        if name := self._name:
            return name if isinstance(name, Name) else Name(name)
        return Name()

    @cached_property
    def name(self):
        return Name.from_parts(tuple(map(combine_with_parens, _name_parts(self.name_base, self.edition))))

    def full_name(self, hide_edition=False):
        return combine_with_parens(map(combine_with_parens, _name_parts(self.name_base, self.edition, hide_edition)))

    @cached_property
    def cls_type_name(self):
        return self.entry.cls_type_name + 'Edition'

    @cached_property
    def artists(self) -> Set['Artist']:
        artists = set()
        if isinstance(self._artist, Artist):
            artists.add(self._artist)
        elif isinstance(self._artist, set):
            artist_links, artist_strs = set(), set()
            for artist in self._artist:
                if isinstance(artist, Link):
                    artist_links.add(artist)
                else:
                    artist_strs.add(artist)
            if artist_strs:
                log.debug(f'Found non-link artist values for {self!r}: {artist_strs}', extra={'color': 11})
            artists.update(Artist.from_links(artist_links).values())
        elif isinstance(self._artist, Link):
            try:
                artists.add(Artist.from_link(self._artist))
            except BadLinkError as e:
                log.debug(f'Error getting artist={self._artist} for {self}: {e}')
        else:
            log.debug(f'Found unexpected value for {self!r}._artist: {self._artist!r}', extra={'color': 11})
        return artists

    @cached_property
    def artist(self) -> Optional['Artist']:
        if artists := self.artists:
            if len(artists) == 1:
                return next(iter(artists))
            else:
                log.debug(f'Multiple artists found for {self!r}: {artists}')
        else:
            log.debug(f'No artists found for {self!r}')
        return None

    @cached_property
    def date(self) -> date:
        return min(self.release_dates)

    @cached_property
    def parts(self) -> List['DiscographyEntryPart']:
        if parser := WikiParser.for_site(self.page.site, 'process_edition_parts'):
            return list(parser.process_edition_parts(self))
        else:
            log.debug(f'No discography entry part extraction is configured for {self.page}')
            return []

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
        ed = self.edition
        return Name.from_parts(tuple(map(combine_with_parens, _name_parts(ed.name_base, ed.edition, part=self._name))))

    @cached_property
    def cls_type_name(self):
        return self.edition.entry.cls_type_name + 'Part'

    def full_name(self, hide_edition=False):
        ed = self.edition
        return combine_with_parens(
            map(combine_with_parens, _name_parts(ed.name_base, ed.edition, hide_edition, self._name))
        )

    @cached_property
    def track_names(self) -> List[Name]:
        if parser := WikiParser.for_site(self.edition.page.site, 'parse_track_name'):
            return [parser.parse_track_name(node) for node in self._tracks.iter_flat()]
        else:
            log.debug(f'No track name extraction is configured for {self.edition.page}')
            return []

    @cached_property
    def tracks(self) -> List['Track']:
        return [Track(i + 1, name, self) for i, name in enumerate(self.track_names)]


class SoundtrackPart(DiscographyEntryPart):
    """A part of a multi-part soundtrack"""
    pass


def _name_parts(
        base: Name, edition: Optional[str] = None, hide_edition=False, part: Optional[str] = None
) -> Tuple[Tuple[str, ...], ...]:
    eng, non_eng = (base.english, base.non_eng)
    edition = None if hide_edition else edition
    part_filter = lambda *parts: tuple(filter(None, parts))
    if eng and non_eng:
        return part_filter(part_filter(eng, part, edition), part_filter(non_eng, part, edition))
    elif name := eng or non_eng:
        return part_filter(part_filter(name, part, edition))
    else:
        return part_filter(part_filter(part, edition))


# Down here due to circular dependency
from .artist import Artist
from .track import Track
