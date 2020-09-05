"""
:author: Doug Skrypa
"""

import logging
import re
from datetime import datetime, date
from functools import cached_property
from typing import List, Optional, Tuple, Sequence, Iterator, MutableSet, Set, Union, Iterable, Any

from ordered_set import OrderedSet

from ds_tools.utils.misc import num_suffix
from wiki_nodes import MediaWikiClient, WikiPage, PageMissingError
from wiki_nodes.nodes import Node, Link, List as ListNode, CompoundNode, String, Table
from ..common import DiscoEntryType
from ..text import combine_with_parens, Name, strip_enclosed
from .base import EntertainmentEntity, Pages, TVSeries
from .disco_entry import DiscoEntry
from .exceptions import EntityTypeError, BadLinkError
from .parsing import WikiParser
from .utils import short_site

__all__ = [
    'DiscographyEntry', 'DiscographyEntryEdition', 'DiscographyEntryPart',
    'Soundtrack', 'SoundtrackEdition', 'SoundtrackPart',
    'Album', 'Single',
]
log = logging.getLogger(__name__)
OST_MATCH = re.compile(r'^(.*? OST) (PART.?\s?\d+)$').match
NodeOrNodes = Union[Node, Iterable[Node], None]
ListOrLists = Union[ListNode, Iterable[ListNode], None]
NameType = Union[str, Name, None]
TrackNodes = Union[Table, ListNode, None]


class DiscographyEntry(EntertainmentEntity):
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
        sites = ', '.join(sorted(short_site(site) for site in self._pages))
        page_str = 'pages (0)' if not sites else f'pages ({len(self._pages)}): {sites}'
        return f'<[{self.date_str}]{self.cls_type_name}({self.names_str!r})[{page_str}]>'

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
    def _merge_key(self) -> Tuple[Optional[int], str, Optional['DiscoEntryType']]:
        uc_name = self._name.upper()
        if ost_match := OST_MATCH(uc_name):
            uc_name = ost_match.group(1)
        return self.year, uc_name, self.type

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
    def from_disco_entry(cls, disco_entry: 'DiscoEntry', **kwargs) -> 'DiscographyEntry':
        log.debug(f'Creating {cls.__name__} from {disco_entry} with {kwargs=}', extra={'color': 14})
        try:
            return cls._by_category(disco_entry, disco_entry=disco_entry, **kwargs)
        except EntityTypeError as e:
            log.error(f'Failed to create {cls.__name__} from {disco_entry}: {e}', extra={'color': 9})
            # log.error(f'Failed to create {cls.__name__} from {disco_entry}: {e}', stack_info=True, extra={'color': 9})
            raise

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._type = DiscoEntryType.Soundtrack

    def split_editions(self):
        full, parts = None, None
        for edition in self.editions:
            # noinspection PyUnresolvedReferences
            if edition.full_ost:
                full = edition
            else:
                parts = edition
        return full, parts

    @classmethod
    def from_name(cls, name: str) -> 'Soundtrack':
        client = MediaWikiClient('wiki.d-addicts.com')
        results = client.get_pages(name, search=True, gsrwhat='text')
        log.debug(f'Search results for {name=!r}: {results}')
        for title, page in results.items():
            try:
                return cls._by_category(page)
            except EntityTypeError:
                try:
                    show = TVSeries._by_category(page)
                except EntityTypeError:
                    log.debug(f'Found {page=!r} that is neither an OST or a TVSeries')
                else:
                    return cls.find_from_links(show.soundtrack_links())

        raise ValueError(f'No pages were found for OSTs matching {name!r}')


# noinspection PyUnresolvedReferences
class _ArtistMixin:
    @cached_property
    def artists(self) -> Set['Artist']:
        artists = set()
        if isinstance(self._artist, Artist):
            artists.add(self._artist)
        elif isinstance(self._artist, (set, CompoundNode)):
            artist_links, artist_strs = set(), set()
            for artist in self._artist:
                if isinstance(artist, Link):
                    artist_links.add(artist)
                elif isinstance(artist, String) and artist.value == ',':
                    pass
                else:
                    artist_strs.add(artist)
            if artist_strs:
                log.debug(f'Found non-link artist values for {self._basic_repr}: {artist_strs}', extra={'color': 11})

            strict = 0 if artists or len(artist_links) > 1 else 1
            log.debug(f'Looking for artists from links: {artist_links} {strict=!r}')
            artists.update(Artist.from_links(artist_links, strict=strict).values())
        elif isinstance(self._artist, Link):
            try:
                artists.add(Artist.from_link(self._artist))
            except (BadLinkError, PageMissingError, EntityTypeError) as e:
                log.debug(f'Error getting artist={self._artist} for {self._basic_repr}: {e}')
        else:
            log.debug(f'Found unexpected value for {self._basic_repr}._artist: {self._artist!r}', extra={'color': 11})
        return artists

    @cached_property
    def artist(self) -> Optional['Artist']:
        if artists := self.artists:
            if len(artists) == 1:
                return next(iter(artists))
            else:
                log.debug(f'Multiple artists found for {self._basic_repr}: {artists}')
        else:
            log.debug(f'No artists found for {self._basic_repr}')
        return None


class DiscographyEntryEdition(_ArtistMixin):
    """An edition of an album"""
    def __init__(
        self,
        name: NameType,
        page: WikiPage,
        entry: DiscographyEntry,
        entry_type: 'DiscoEntryType',
        artist: NodeOrNodes,
        release_dates: Sequence[date],
        content: Any,
        edition: Optional[str] = None,
        lang: Optional[str] = None,
        repackage=False,
    ):
        self._name = name                                                                   # type: NameType
        self.page = page                                                                    # type: WikiPage
        self.entry = entry                                                                  # type: DiscographyEntry
        self.type = entry_type                                                              # type: DiscoEntryType
        self._artist = artist                                                               # type: NodeOrNodes
        self.release_dates = release_dates                                                  # type: Sequence[date]
        self._content = content
        self.edition = edition                                                              # type: Optional[str]
        self.repackage = repackage                                                          # type: bool
        self._lang = lang                                                                   # type: Optional[str]
        log.debug(f'Created {self.__class__.__name__} with {release_dates=!r} {name=!r} {edition=!r} {entry_type=!r}')

    @property
    def _basic_repr(self):
        # Used in logs from .artists and .artist to avoid circular references that depend on artist being set
        try:
            _date = self.release_dates[0].strftime('%Y-%m-%d')
        except IndexError:
            _date = None
        edition = f'[edition={self.edition!r}]' if self.edition else ''
        lang = f'[lang={self._lang!r}]' if self._lang else ''
        return f'<[{_date}]{self.cls_type_name}[{self._name!r} @ {self.page}]{edition}{lang}>'

    def __repr__(self) -> str:
        _date = self.release_dates[0].strftime('%Y-%m-%d') if self.release_dates else None
        _type = self.numbered_type or (repr(self.type.real_name) if self.type else None)
        alb_type = f'[type={_type}]' if _type else ''
        _edition = self.edition or ''
        if self.repackage:
            _edition = f'{_edition}, repackage' if _edition else 'repackage'
        edition = f'[edition={_edition!r}]' if _edition else ''
        lang = f'[lang={self._lang!r}]' if self._lang else ''
        return f'<[{_date}]{self.cls_type_name}[{self._name!r} @ {self.page}]{alb_type}{edition}{lang}>'

    def __eq__(self, other):
        return self.__class__ == other.__class__ and self.page == other.page and self.edition == other.edition

    def __hash__(self):
        return hash((self.__class__, self.page, self.edition))

    def __iter__(self) -> Iterator['DiscographyEntryPart']:
        return iter(self.parts)

    def __bool__(self):
        return bool(self.parts)

    @property
    def __cmp_tuple(self):
        return self.page, self.artist, self.date, self._name, self.edition

    def __lt__(self, other: 'DiscographyEntryEdition') -> bool:
        return self.__cmp_tuple < other.__cmp_tuple

    @cached_property
    def lang(self) -> Optional[str]:
        if lang := self._lang:
            return lang
        if artist := self.artist:
            lang = artist.language
        return 'Korean' if not lang and self.page.site == 'kpop.fandom.com' else lang

    @cached_property
    def name_base(self) -> Name:
        if name := self._name:
            return name if isinstance(name, Name) else Name(name)
        return Name()

    @cached_property
    def name(self):
        return Name.from_parts(tuple(map(combine_with_parens, _name_parts(self.name_base, self.edition))))

    def full_name(self, hide_edition=False) -> str:
        if (edition := self.edition) and edition.lower().endswith(' repackage'):    # Named repackage
            return edition[:-10].strip()
        return combine_with_parens(map(combine_with_parens, _name_parts(self.name_base, self.edition, hide_edition)))

    @cached_property
    def cls_type_name(self):
        return self.entry.cls_type_name + 'Edition'

    @cached_property
    def date(self) -> Optional[date]:
        try:
            return min(self.release_dates)
        except ValueError as e:
            log.error(f'Error determining release date for {self._basic_repr}: {e}')
            return None

    @cached_property
    def parts(self) -> List['DiscographyEntryPart']:
        if parser := WikiParser.for_site(self.page.site, 'process_edition_parts'):
            return list(parser.process_edition_parts(self))
        else:
            log.debug(f'No discography entry part extraction is configured for {self.page}')
            return []

    @property
    def number(self) -> Optional[int]:
        return self.entry.number

    @cached_property
    def numbered_type(self) -> Optional[str]:
        if (num := self.entry.number) and self.type:
            album_lang = self.lang
            artist_lang = self.artist.language if self.artist else None
            log.debug(f'{self._basic_repr} {album_lang=!r} {artist_lang=!r}')
            parts = (
                f'{num}{num_suffix(num)}',
                None if artist_lang and album_lang and artist_lang == album_lang else album_lang,
                self.type.real_name, 'Repackage' if self.repackage else None
            )
            return ' '.join(filter(None, parts))
        return None


class SoundtrackEdition(DiscographyEntryEdition):
    """An edition of a soundtrack (full / parts)"""

    @property
    def full_ost(self):
        return self.edition == '[Full OST]'


class DiscographyEntryPart:
    ost = False
    _disc_match = re.compile('(?:DVD|CD|Dis[ck])\s*(\d+)', re.IGNORECASE).match

    def __init__(
        self,
        name: Optional[str],
        edition: DiscographyEntryEdition,
        tracks: TrackNodes,
        disc: Optional[int] = None,
    ):
        self._name = name                                   # type: Optional[str]
        self.edition = edition                              # type: DiscographyEntryEdition
        self._tracks = tracks                               # type: TrackNodes
        if disc is not None:
            self.disc = disc                                # type: int
        else:
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

    def __eq__(self, other):
        return self.__class__ == other.__class__ and self._name == other._name and self.edition == other.edition

    def __hash__(self):
        return hash((self.__class__, self._name, self.edition))

    def __iter__(self) -> Iterator['Track']:
        return iter(self.tracks)

    def __bool__(self):
        return bool(self.tracks)

    def __len__(self):
        return len(self.track_names)

    _basic_repr = property(__repr__)

    @cached_property
    def repackage(self):
        return bool(self.edition.repackage)

    @cached_property
    def name(self):
        ed = self.edition
        return Name.from_parts(tuple(map(combine_with_parens, _name_parts(ed.name_base, ed.edition, part=self._name))))

    @cached_property
    def cls_type_name(self):
        return self.edition.entry.cls_type_name + 'Part'

    def full_name(self, hide_edition=False):
        ed = self.edition
        edition_str = ed.edition
        if edition_str and edition_str.lower().endswith(' repackage'):  # Named repackage
            base = Name(edition_str[:-10].strip())
            edition_str = None
        else:
            base = ed.name_base
            if self.repackage:
                edition_str = f'{edition_str} - Repackage' if edition_str else 'Repackage'

        part = None if self.ost else self._name
        full_name = combine_with_parens(map(combine_with_parens, _name_parts(base, edition_str, hide_edition, part)))
        if self.ost and self._name:
            full_name += f' - {self._name}'
        return full_name

    @cached_property
    def track_names(self) -> List[Name]:
        if parser := WikiParser.for_site(self.edition.page.site, 'parse_track_name'):
            if self._tracks is None:
                if self.edition.type == DiscoEntryType.Single:
                    return [parser.parse_single_page_track_name(self.edition.page)]
                else:
                    log.debug(f'No tracks found for {self}')
            else:
                if isinstance(self._tracks, Table):
                    return [parser.parse_track_name(row) for row in self._tracks]
                else:
                # if isinstance(self._tracks, ListNode):
                    return [parser.parse_track_name(node) for node in self._tracks.iter_flat()]
        else:
            log.debug(f'No track name extraction is configured for {self.edition.page}')
        return []

    @cached_property
    def tracks(self) -> List['Track']:
        tracks = [Track(i + 1, name, self) for i, name in enumerate(self.track_names)]
        eng_non_eng_map = {}
        for track in tracks:
            eng, non_eng = track.name.english, track.name.non_eng
            if eng and non_eng:
                eng_non_eng_map[eng] = non_eng
            elif eng and eng in eng_non_eng_map:
                track.name.non_eng = eng_non_eng_map[eng]
        return tracks


class SoundtrackPart(DiscographyEntryPart, _ArtistMixin):
    """A part of a multi-part soundtrack"""
    ost = True

    def __init__(self, part: Optional[int], *args, artist: NodeOrNodes = None, **kwargs):
        DiscographyEntryPart.__init__(self, *args, **kwargs)
        self.part = part
        self._artist = artist


def _strip(text):
    if text:
        return strip_enclosed(text, exclude='])')
    return text


def _name_parts(
        base: Name, edition: Optional[str] = None, hide_edition=False, part: Optional[str] = None
) -> Tuple[Tuple[str, ...], ...]:
    eng, non_eng = (_strip(base.english), _strip(base.non_eng))
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
