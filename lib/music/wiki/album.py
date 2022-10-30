"""
:author: Doug Skrypa
"""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from datetime import datetime, date
from itertools import chain
from typing import TYPE_CHECKING, Optional, Iterator, MutableSet, Union, Iterable, Any

from ordered_set import OrderedSet

from ds_tools.caching.decorators import cached_property
from ds_tools.utils.misc import num_suffix
from wiki_nodes import MediaWikiClient, WikiPage, PageMissingError
from wiki_nodes.exceptions import BadLinkError
from wiki_nodes.nodes import Node, Link, List as ListNode, CompoundNode, String, Table, Template

from ..common.disco_entry import DiscoEntryType
from ..text.extraction import strip_enclosed
from ..text.name import Name
from ..text.utils import combine_with_parens
from .base import EntertainmentEntity, Pages, TVSeries
from .exceptions import EntityTypeError, AmbiguousWikiPageError, NoLinkedPagesFoundError
from .parsing import WikiParser, RawTracks
from .utils import short_site

if TYPE_CHECKING:
    from .disco_entry import DiscoEntry
    from .typing import StrDateMap, OptStr

__all__ = [
    'DiscographyEntry', 'DiscographyEntryEdition', 'DiscographyEntryPart', 'DEEdition', 'DEPart', 'DiscoObj',
    'Soundtrack', 'SoundtrackEdition', 'SoundtrackPart',
    'Album', 'Single',
]
log = logging.getLogger(__name__)

OST_MATCH = re.compile(r'^(.*? OST) (PART.?\s?\d+)$').match

NodeOrNodes = Union[Node, Iterable[Node], None]
ListOrLists = Union[ListNode, Iterable[ListNode], None]
NameType = Union[str, Name, None]
TrackNodes = Union[Table, ListNode, None]


# region Discography Entry (Album)


class DiscographyEntry(EntertainmentEntity):
    """
    A page or set of pages for any item in an artist's top-level discography, i.e., albums, soundtracks, singles,
    collaborations.

    Individual tracks are represented by :class:`Track<.track.Track>` objects.

    :param name: The name of this discography entry
    :param pages: One or more WikiPage objects
    :param disco_entry: The :class:`DiscoEntry<.disco_entry.DiscoEntry>` containing the Node and metadata
      from the artist or Discography page about this entry.
    :param artist: The :class:`Artist<.artist.Artist>` whose page contained this entry
    :param entry_type: The :class:`DiscoEntryType<.common.disco_entry.DiscoEntryType>` from the discography section
      containing this entry
    """
    _categories = ()
    disco_entries: list[DiscoEntry]
    _date: Optional[date]
    _artist: Optional[Artist]
    _type: Optional[DiscoEntryType]

    def __init__(
        self,
        name: str = None,
        pages: Pages = None,
        disco_entry: DiscoEntry = None,
        artist: Artist = None,
        entry_type: DiscoEntryType = None,
    ):
        if name and name[0] == name[-1] == '"':
            name = name[1:-1]
        super().__init__(name, pages)
        self.disco_entries = [disco_entry] if disco_entry else []
        self._date = None
        self._artist = artist
        self._type = entry_type

    @classmethod
    def from_disco_entry(cls, disco_entry: DiscoEntry, **kwargs) -> DiscographyEntry:
        log.debug(f'Creating {cls.__name__} from {disco_entry} with {kwargs=}', extra={'color': 14})
        try:
            return cls._by_category(disco_entry, disco_entry=disco_entry, **kwargs)
        except EntityTypeError as e:
            log.error(f'Failed to create {cls.__name__} from {disco_entry}: {e}', extra={'color': 9})
            # log.error(f'Failed to create {cls.__name__} from {disco_entry}: {e}', stack_info=True, extra={'color': 9})
            raise

    # region Internal Methods

    def __repr__(self) -> str:
        sites = ', '.join(sorted(short_site(site) for site in self._pages))
        page_str = 'pages (0)' if not sites else f'pages ({len(self._pages)}): {sites}'
        return f'<[{self.date_str}]{self.cls_type_name}({self.names_str!r})[{page_str}]>'

    @property
    def _basic_repr(self) -> str:
        # Used in logs to avoid circular references that depend on editions being set
        sites = ', '.join(sorted(short_site(site) for site in self._pages))
        page_str = 'pages (0)' if not sites else f'pages ({len(self._pages)}): {sites}'
        date_str = self._date.strftime('%Y-%m-%d') if self._date else str(self.year)
        name_str = str(Name(self._name))
        return f'<[{date_str}]{self.cls_type_name}({name_str!r})[{page_str}]>'

    @cached_property
    def _sort_key(self) -> tuple[int, date, Name]:
        release_date = self.date or datetime.fromtimestamp(0).date()
        return self.year or release_date.year, release_date, self.name

    def __lt__(self, other: DiscographyEntry) -> bool:
        return self._sort_key < other._sort_key

    def __iter__(self) -> Iterator[DiscographyEntryEdition]:
        """Iterate over every edition part in this DiscographyEntry"""
        return iter(self.editions)

    def __bool__(self) -> bool:
        return bool(self.editions)

    @cached_property
    def _merge_key(self) -> tuple[Optional[int], str, Optional[DiscoEntryType]]:
        """Used by :meth:`.DiscographyMixin.discography`"""
        uc_name = self._name.upper()
        if ost_match := OST_MATCH(uc_name):
            uc_name = ost_match.group(1)
        return self.year, uc_name, self.type

    def _merge(self, other: DiscographyEntry):
        self._pages.update(other._pages)
        self.disco_entries.extend(other.disco_entries)
        self.clear_cached_properties()

    # endregion

    # region Name

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
    def names_str(self) -> str:
        names = self.names or [self.name]
        return ' / '.join(map(str, names))

    # endregion

    # region Artist, Type, Number

    @cached_property
    def artists(self) -> set[Artist]:
        artists = set()
        if isinstance(self._artist, Artist):
            artists.add(self._artist)
        for edition in self.editions:
            artists.update(edition.artists)
        return artists

    @cached_property
    def artist(self) -> Optional[Artist]:
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
    def type(self) -> Optional[DiscoEntryType]:
        if isinstance(self._type, DiscoEntryType):
            return self._type
        for edition in self.editions:
            if edition.type:
                return edition.type
        return None

    @cached_property
    def cls_type_name(self) -> str:
        return self.type.name if self.type else self.__class__.__name__

    @cached_property
    def number(self) -> Optional[int]:
        for page, parser in self.page_parsers('parse_album_number'):
            return parser.parse_album_number(page)
        return None

    # endregion

    # region Release Date

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

    # endregion

    @cached_property
    def editions(self) -> list[DiscographyEntryEdition]:
        editions = []
        for entry_page, parser in self.page_parsers('process_album_editions'):
            editions.extend(parser.process_album_editions(self, entry_page))
        return editions

    def parts(self) -> Iterator[DiscographyEntryPart]:
        for edition in self.editions:
            yield from edition


class Album(DiscographyEntry):
    """An album or mini album or EP, or a repackage thereof"""
    _categories = ('album', 'extended play', ' eps', '-language eps', 'mixtape')

    @classmethod
    def from_name(cls, name: str) -> Album:
        client = MediaWikiClient('kpop.fandom.com')
        # results = client.get_pages(name, search=True, gsrwhat='text')
        results = client.get_pages(name, search=True)
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

        raise ValueError(f'No pages were found for {cls.__name__}s matching {name!r}')


class Single(DiscographyEntry):
    _categories = ('single', 'song', 'collaboration', 'feature')
    _not_categories = ('songwriter',)


class Soundtrack(DiscographyEntry):
    _categories = ('ost', 'soundtrack')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._type = DiscoEntryType.Soundtrack

    def split_editions(self):
        full, parts, extras = None, None, None
        for edition in self.editions:
            if getattr(edition, 'full_ost', True):  # If it is not a DramaWiki soundtrack with this attr, treat as full
                full = edition
            elif getattr(edition, 'ost_extras', False):
                extras = edition
            else:
                parts = edition
        return full, parts, extras

    @classmethod
    def from_name(cls, name: str) -> Soundtrack:
        client = MediaWikiClient('wiki.d-addicts.com')
        results = client.get_pages(name, search=True, gsrwhat='text')
        log.debug(f'Search results for {name=!r}: {results}')
        last_error = None
        for title, page in results.items():
            try:
                return cls._by_category(page)
            except EntityTypeError:
                try:
                    show = TVSeries._by_category(page)
                except EntityTypeError:
                    log.debug(f'Found {page=!r} that is neither an OST or a TVSeries')
                else:
                    try:
                        return cls.find_from_links(show.soundtrack_links())
                    except NoLinkedPagesFoundError as e:
                        e.source = page
                        last_error = e

        if last_error is not None:
            raise last_error
        raise ValueError(f'No pages were found for OSTs matching {name!r}')

    @cached_property
    def tv_series(self) -> Optional[TVSeries]:
        for entry_page, parser in self.page_parsers('parse_source_show'):
            try:
                if series := parser.parse_source_show(entry_page):
                    return series
            except Exception as e:
                log.debug(f'Error finding TV series for {self}: {e}')
        return None


# endregion


class _ArtistMixin(ABC):
    @property
    @abstractmethod
    def date(self) -> Optional[date]:
        raise NotImplementedError

    @property
    @abstractmethod
    def _basic_repr(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def _artist(self):
        raise NotImplementedError

    @property
    def track_artists(self) -> set[Artist]:
        return set()

    @cached_property
    def _artists(self) -> set[Artist]:
        log.debug(f'{self._basic_repr}: Processing {self._artist}', extra={'color': 13})
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
            try:
                artists.update(Artist.from_links(artist_links, strict=strict).values())
            except AmbiguousWikiPageError as e:
                e.add_context(f'While processing {self._basic_repr}._artists {artist_links=}')
                raise
        elif isinstance(self._artist, Link):
            try:
                artists.add(Artist.from_link(self._artist))
            except (BadLinkError, PageMissingError, EntityTypeError) as e:
                log.debug(f'Error getting artist={self._artist} for {self._basic_repr}: {e}')
            except AmbiguousWikiPageError as e:
                e.add_context(f'While looking for {self._basic_repr}._artist={self._artist}')
                raise
        else:
            log.debug(f'Found unexpected value for {self._basic_repr}._artist: {self._artist!r}', extra={'color': 11})
        return artists

    @cached_property
    def artists(self) -> set[Artist]:
        if artists := self._artists:
            return artists
        elif artists := self.track_artists:
            return artists
        return set()

    @cached_property
    def artist(self) -> Optional[Artist]:
        if artists := self.artists:
            if len(artists) == 1:
                return next(iter(artists))
            else:
                log.debug(f'Multiple artists found for {self._basic_repr}: {artists}', extra={'color': 11})
        else:
            log.debug(f'No artists found for {self._basic_repr}', extra={'color': 11})
        return None

    @cached_property
    def date_str(self) -> OptStr:
        try:
            return self.date.strftime('%Y-%m-%d')
        except AttributeError:
            return None


# region Editions


class DiscographyEntryEdition(_ArtistMixin):
    """An edition of an album"""

    _name: NameType
    page: WikiPage
    entry: DiscographyEntry
    type: DiscoEntryType
    _artist: NodeOrNodes = None  # = None is required to satisfy the abstract property
    release_dates: StrDateMap
    _content: Any
    edition: OptStr
    repackage: bool
    _lang: OptStr

    def __init__(
        self,
        name: NameType,
        page: WikiPage,
        entry: DiscographyEntry,
        entry_type: DiscoEntryType,
        artist: NodeOrNodes,
        release_dates: StrDateMap,
        content: Any,
        edition: str = None,
        lang: str = None,
        repackage: bool = False,
    ):
        self._name = name
        self.page = page
        self.entry = entry
        self.type = entry_type
        self._artist = artist
        self.release_dates = release_dates
        self._content = content
        self.edition = edition
        self.repackage = repackage
        self._lang = lang
        # log.debug(f'Created {self.__class__.__name__} with {release_dates=} {name=} {edition=} {entry_type=}')

    # region Internal Methods

    @property
    def _basic_repr(self) -> str:
        # Used in logs from .artists and .artist to avoid circular references that depend on artist being set
        edition = f'[edition={self.edition!r}]' if self.edition else ''
        lang = f'[lang={self._lang!r}]' if self._lang else ''
        return f'<[{self.date_str}]{self.cls_type_name}[{self._name!r} @ {self.page}]{edition}{lang}>'

    def __repr__(self) -> str:
        _type = self.numbered_type or (repr(self.type.real_name) if self.type else None)
        alb_type = f'[type={_type}]' if _type else ''
        edition = self.edition or ''
        if self.repackage:
            edition = f'{edition}, repackage' if edition else 'repackage'
        edition = f'[{edition=}]' if edition else ''
        lang = f'[lang={self._lang!r}]' if self._lang else ''
        return f'<[{self.date_str}]{self.cls_type_name}[{self._name!r} @ {self.page}]{alb_type}{edition}{lang}>'

    def __eq__(self, other) -> bool:
        return self.__class__ == other.__class__ and self.page == other.page and self.edition == other.edition

    def __hash__(self) -> int:
        return hash(self.__class__) ^ hash(self.page) ^ hash(self.edition)

    def __iter__(self) -> Iterator[DiscographyEntryPart]:
        return iter(self.parts)

    def __bool__(self) -> bool:
        return bool(self.parts)

    @property
    def __cmp_tuple(self):
        return self.page, self.artist, self.date, self._name, self.edition

    def __lt__(self, other: DiscographyEntryEdition) -> bool:
        return self.__cmp_tuple < other.__cmp_tuple

    # endregion

    # region Language Methods

    @cached_property
    def lang(self) -> OptStr:
        if lang := self._lang:
            return lang
        if artist := self.artist:
            if self.page.site == 'www.generasia.com':
                lang = self._get_lang_from_artist_template()
            lang = lang or artist.language
        return 'Korean' if not lang and self.page.site == 'kpop.fandom.com' else lang

    def _get_artist_template_page(self) -> Optional[WikiPage]:
        for tmpl in self.page.sections.find_all(Template, True):
            if tmpl.name == self.artist.name.english and tmpl.value is None:
                mwc = MediaWikiClient(tmpl.root.site)
                return mwc.get_page(f'Template:{tmpl.name}')

        return None

    def _get_lang_from_artist_template(self) -> OptStr:
        if not (page := self._get_artist_template_page()):
            return None

        for section, values in page.sections.content.zipped.items():
            if lang := next((val for val in ('Korean', 'Japanese') if section.startswith(val)), None):
                if isinstance(values, Link):
                    if self.page.title == values.title:
                        return lang
                elif isinstance(values, Node):
                    if values.find_one(Link, recurse=True, title=self.page.title):
                        return lang
                else:
                    try:
                        for obj in values:  # noqa
                            if isinstance(obj, Link) and self.page.title == obj.title:
                                return lang
                    except TypeError:
                        pass

        return None

    # endregion

    # region Name

    @cached_property
    def name_base(self) -> Name:
        if name := self._name:
            return name if isinstance(name, Name) else Name(name)
        return Name()

    @cached_property
    def name(self) -> Name:
        return Name.from_parts(tuple(map(combine_with_parens, _name_parts(self.name_base, self.edition))))

    def full_name(self, hide_edition: bool = False) -> str:
        if (edition := self.edition) and edition.lower().endswith(' repackage'):    # Named repackage
            return edition[:-10].strip()
        return combine_with_parens(map(combine_with_parens, _name_parts(self.name_base, self.edition, hide_edition)))

    # endregion

    # region Release Date

    @cached_property
    def date(self) -> Optional[date]:
        if not (release_dates := self.release_dates):
            return None
        if isinstance(edition := self.edition, str):
            editions = (edition.casefold(), None)
        else:
            editions = (None,)

        for edition in editions:
            try:
                return release_dates[edition]
            except KeyError:
                pass
        try:
            return min(release_dates.values())
        except ValueError as e:
            log.error(f'Error determining release date for {self._basic_repr}: {e}')
            return None

    @cached_property
    def date_str(self) -> OptStr:
        try:
            return self.date.strftime('%Y-%m-%d')
        except AttributeError:
            return None

    # endregion

    @cached_property
    def track_artists(self) -> set[Artist]:
        return set(chain.from_iterable(part.track_artists for part in self.parts))

    @cached_property
    def parts(self) -> list[DiscographyEntryPart]:
        if parser := WikiParser.for_site(self.page.site, 'process_edition_parts'):
            return list(parser.process_edition_parts(self))
        else:
            log.debug(f'No discography entry part extraction is configured for {self.page}')
            return []

    # region Number and Type

    @cached_property
    def cls_type_name(self) -> str:
        return self.entry.cls_type_name + 'Edition'

    @property
    def number(self) -> Optional[int]:
        return self.entry.number

    @cached_property
    def numbered_type(self) -> OptStr:
        if (num := self.entry.number) and self.type:
            album_lang = self.lang
            artist_lang = self.artist.language if self.artist else None
            log.debug(f'{self._basic_repr} {album_lang=!r} {artist_lang=!r}')
            parts = (
                f'{num}{num_suffix(num)}',
                None if artist_lang and album_lang and artist_lang == album_lang else album_lang,
                self.type.real_name,
                'Repackage' if self.repackage else None,
            )
            return ' '.join(filter(None, parts))

        return None

    @property
    def full_ost(self) -> bool:
        return self.edition in {'[Full OST]', 'Full OST'}

    # endregion


class SoundtrackEdition(DiscographyEntryEdition):
    """An edition of a soundtrack (full / parts / extras)"""
    entry: Soundtrack
    parts: list[SoundtrackPart]

    @cached_property
    def name_base(self) -> Name:
        name_base = super().name_base
        if name_base.has_romanization(name_base.english) and (tv_series := self.entry.tv_series):
            if (series_eng := tv_series.name.english) and not name_base.english.startswith(series_eng):
                ost_suffix = ' OST' if name_base.english.endswith(' OST') else ''
                return name_base.with_part(_english=series_eng + ost_suffix)
        return name_base

    @property
    def ost_extras(self) -> bool:
        return self.edition == '[Extra Parts]'


# endregion

# region Parts


class DiscographyEntryPart(_ArtistMixin):
    ost = False
    _disc_match = re.compile(r'(?:DVD|CD|Dis[ck])\s*(\d+)', re.IGNORECASE).match
    _name: OptStr
    edition: DiscographyEntryEdition
    _tracks: RawTracks
    _date: Optional[date]
    _artist: NodeOrNodes = None  # = None is required to satisfy the abstract property
    disc: int

    def __init__(
        self,
        name: OptStr,
        edition: DiscographyEntryEdition,
        tracks: RawTracks,
        disc: int = None,
        release_date: date = None,
        artist: NodeOrNodes = None,
    ):
        self._name = name
        self.edition = edition
        self._tracks = tracks
        self._date = release_date
        self._artist = artist
        if disc is not None:
            self.disc = disc
        else:
            m = self._disc_match(name) if name else None
            self.disc = int(m.group(1)) if m else 1

    # region Internal Methods

    def __repr__(self) -> str:
        ed = self.edition
        edition = f'[edition={ed.edition!r}]' if ed.edition else ''
        name = f'[{self._name}]' if self._name else ''
        return f'<[{ed.date_str}]{self.cls_type_name}[{ed._name!r} @ {ed.page}]{edition}{name}>'

    def __lt__(self, other: DiscographyEntryPart) -> bool:
        return (self.edition, self._name) < (other.edition, other._name)

    def __eq__(self, other) -> bool:
        return self.__class__ == other.__class__ and self._name == other._name and self.edition == other.edition

    def __hash__(self) -> int:
        return hash(self.__class__) ^ hash(self._name) ^ hash(self.edition)

    def __iter__(self) -> Iterator[Track]:
        return iter(self.tracks)

    def __bool__(self) -> bool:
        return bool(self.tracks)

    def __len__(self) -> int:
        return len(self.track_names)

    _basic_repr = property(__repr__)

    # endregion

    @property
    def page(self) -> WikiPage:
        return self.edition.page

    @property
    def is_ost(self) -> bool:
        if self.ost:
            return True
        return self.edition.type == DiscoEntryType.Soundtrack

    @cached_property
    def date(self) -> Optional[date]:
        if self._date:
            return self._date
        return self.edition.date

    @cached_property
    def repackage(self) -> bool:
        return bool(self.edition.repackage)

    @cached_property
    def name(self) -> Name:
        ed = self.edition
        return Name.from_parts(tuple(map(combine_with_parens, _name_parts(ed.name_base, ed.edition, part=self._name))))

    @cached_property
    def cls_type_name(self) -> str:
        return self.edition.entry.cls_type_name + 'Part'

    def full_name(self, hide_edition: bool = False) -> str:
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
    def track_artists(self) -> set[Artist]:
        return set(chain.from_iterable(track.artists for track in self.tracks))

    @cached_property
    def track_names(self) -> list[Name]:
        if parser := WikiParser.for_site(self.edition.page.site, 'parse_track_name'):
            return self._tracks.get_names(self, parser)
        else:
            log.debug(f'No track name extraction is configured for {self.edition.page}')
            return []

    @cached_property
    def tracks(self) -> list[Track]:
        tracks = [Track(i + 1, name, self) for i, name in enumerate(self.track_names)]
        eng_non_eng_map = {}
        for track in tracks:
            eng, non_eng = track.name.english, track.name.non_eng
            if eng and non_eng:
                eng_non_eng_map[eng] = non_eng
            elif eng and eng in eng_non_eng_map:
                track.name.non_eng = eng_non_eng_map[eng]
        return tracks


class SoundtrackPart(DiscographyEntryPart):
    """A part of a multi-part soundtrack"""
    ost = True

    def __init__(self, part: Optional[int], *args, **kwargs):
        DiscographyEntryPart.__init__(self, *args, **kwargs)
        self.part = part


# endregion


DEEdition = Union[DiscographyEntryEdition, SoundtrackEdition]
DEPart = Union[DiscographyEntryPart, SoundtrackPart]
DiscoObj = Union[DiscographyEntry, DEPart, DEEdition]
DEEntryOrEdition = Union[DiscographyEntry, DiscographyEntryEdition]


def _strip(text: str) -> str:
    if text:
        return strip_enclosed(text, exclude='])')
    return text


def _name_parts(
    base: Name, edition: str = None, hide_edition: bool = False, part: str = None
) -> tuple[tuple[str, ...], ...]:
    eng, non_eng = (_strip(base.english), _strip(base.non_eng))
    if hide_edition:
        edition = None
    if eng and non_eng:
        return _part_filter(_part_filter(eng, part, edition), _part_filter(non_eng, part, edition))
    elif name := eng or non_eng:
        return _part_filter(_part_filter(name, part, edition))
    else:
        return _part_filter(_part_filter(part, edition))


def _part_filter(*parts):
    return tuple(part for part in parts if part)


# Down here due to circular dependency
from .artist import Artist
from .track import Track
