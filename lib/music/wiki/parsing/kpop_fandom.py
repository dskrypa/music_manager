"""
:author: Doug Skrypa
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, date
from typing import TYPE_CHECKING, Iterator, Any, Type, Collection

from ds_tools.caching.decorators import cached_property
from ds_tools.unicode import LangCat
from wiki_nodes.exceptions import SiteDoesNotExist
from wiki_nodes.nodes import N, AnyNode, Link, String, CompoundNode, Section, Table, MappingNode, TableSeparator
from wiki_nodes.nodes import Template, Tag, List, ContainerNode
from wiki_nodes.nodes.transformers import dl_keys_to_subsections
from wiki_nodes.page import WikiPage

from music.common.disco_entry import DiscoEntryType
from music.text.extraction import split_enclosed, ends_with_enclosed, has_unpaired, is_enclosed, partition_enclosed
from music.text.extraction import strip_enclosed
from music.text.name import Name
from music.text.time import parse_date, DateResult
from music.text.utils import combine_with_parens, find_ordinal
from ..album import DiscographyEntry, DiscographyEntryEdition, DiscographyEntryPart, SoundtrackPart
from ..base import EntertainmentEntity, GROUP_CATEGORIES, TVSeries
from ..disco_entry import DiscoEntry
from ..exceptions import UnexpectedPageContent
from .abc import WikiParser, EditionIterator
from .utils import PageIntro, RawTracks, get_artist_title, LANG_ABBREV_MAP, find_language, find_nodes

if TYPE_CHECKING:
    from ..discography import DiscographyEntryFinder
    from ..typing import OptStr, StrDateMap

__all__ = ['KpopFandomParser', 'KindieFandomParser']
log = logging.getLogger(__name__)

NodeTypes = Type[AnyNode] | tuple[Type[AnyNode], ...]

DURATION_MATCH = re.compile(r'^(.*?)-\s*(\d+:\d{2})(.*)$').match
MEMBER_TYPE_SECTIONS = {'former': 'Former', 'inactive': 'Inactive', 'sub_units': 'Sub-Units'}
ORD_ALBUM_MATCH = re.compile(r'^\S+(?:st|nd|rd|th)\s+album:?$', re.IGNORECASE).match
RELEASE_DATE_PAT = re.compile(r'((?:[a-z]+(?: \d+)?, )?\d{4})', re.IGNORECASE)
REMAINDER_ARTIST_EXTRA_TYPE_MAP = {'(': 'artists', '(feat.': 'feat', '(sung by': 'artists', '(with': 'collabs'}
UNCLOSED_PAREN_MATCH = re.compile(r'^(.+?)(\([^()]*)$').match
VERSION_SEARCH = re.compile(r'^(.*?(?<!\S)ver(?:\.|sion)?)\)?(.*)$', re.IGNORECASE).match
PART_NUM_SEARCH = re.compile(r'\bpart\.?\s*(\d+)', re.IGNORECASE).search


class KpopFandomParser(WikiParser, site='kpop.fandom.com', domain='fandom.com'):
    __slots__ = ()

    # region Artist Page

    def parse_artist_name(self, artist_page: WikiPage) -> Iterator[Name]:
        yield from PageIntro(artist_page).names()
        if not (infobox_tmpl := artist_page.infobox):
            log.debug(f'No infobox found for {artist_page}')
            return

        # log.debug(f'Found infobox for {artist_page}')
        infobox = infobox_tmpl.value
        if birth_name := infobox.get('birth_name'):
            if isinstance(birth_name, String):
                yield Name.from_enclosed(birth_name.value)
            elif isinstance(birth_name, ContainerNode):
                for line in birth_name:
                    if isinstance(line, String):
                        yield Name.from_enclosed(line.value)
            else:
                raise ValueError(f'Unexpected format for birth_name={birth_name.pformat()}')
        else:
            eng = eng.value if (eng := infobox.get('name')) else None
            non_eng_vals = []
            for script in ('hangul', 'hanja', 'hiragana', 'kanji'):
                if not (node := infobox.get(script)):
                    continue
                elif isinstance(node, String):
                    non_eng_vals.append((script, node.value))
                elif isinstance(node, ContainerNode):    # Example: GWSN - Kanji with Japanese + Chinese
                    non_eng_vals.extend((script, sub_node.value) for sub_node in node if isinstance(sub_node, String))
                else:
                    log.debug(f'Unexpected alt lang name node type on {artist_page}: {script}={node!r}')

            if eng or non_eng_vals:
                non_eng = non_eng_vals.pop(0)[1] if non_eng_vals else None
                yield Name(eng, non_eng, versions={Name(eng, val[1]) for val in non_eng_vals})

    def parse_group_members(self, artist_page: WikiPage) -> dict[str, list[str]]:
        try:
            members_section = artist_page.sections.find('Members')
        except (KeyError, AttributeError):
            log.debug(f'Members section not found for {artist_page}')
            return {}

        # if type(members_section.content) is CompoundNode and
        if (tables := list(members_section.find_all(Table))) and len(tables) == 1:
            log.debug(f'Members section {members_section} => {tables[0]}')
            members_node = tables[0]
        else:
            members_node = members_section.content

        members = {'current': []}
        section = 'current'
        if isinstance(members_node, Table):
            for row in members_node:
                if (
                    isinstance(row, MappingNode)
                    and (name := row.get('Name'))
                    and (title := get_artist_title(name, artist_page))  # noqa
                ):
                    members[section].append(title)
                elif isinstance(row, TableSeparator) and row.value and isinstance(row.value, String):
                    section = row.value.value
                    members[section] = []
        elif members_node:
            for member in members_node.iter_flat():
                if title := get_artist_title(member, artist_page):
                    members['current'].append(title)

        if sub_units_section := artist_page.sections.find('Sub-units', None):
            members['sub_units'] = sub_units = []
            for sub_unit in sub_units_section.content.iter_flat():
                if title := get_artist_title(sub_unit, artist_page):
                    sub_units.append(title)

        return members

    def parse_member_of(self, artist_page: WikiPage) -> Iterator[Link]:
        if not (intro := artist_page.intro()):
            return

        log.debug(f'Looking for groups in intro for {artist_page}', extra={'color': 11})
        try:
            links = intro.find_all(Link, recurse=True)
        except AttributeError:
            log.debug(f'Error finding links on page={artist_page!r} in {intro=}')
        else:
            for link, entity in EntertainmentEntity.from_links(links, strict=0).items():
                # if entity._categories == GROUP_CATEGORIES:
                #     log.debug(f'Found link from {artist_page} to group={entity}', extra={'color': 11})
                if entity._categories == GROUP_CATEGORIES and (members := entity.members):  # noqa
                    log.debug(f'Found link from {artist_page} to group={entity} with {members=}', extra={'color': 11})
                    if any(artist_page == page for m in members for page in m.pages):
                        yield link

    # endregion

    # region High Level Discography

    def process_disco_sections(self, artist_page: WikiPage, finder: DiscographyEntryFinder) -> None:
        ArtistDiscographyParser(artist_page, finder, self).process_disco_sections()

    def parse_disco_page_entries(self, disco_page: WikiPage, finder: DiscographyEntryFinder) -> None:
        # This site does not use discography pages.
        return None

    # endregion

    # region Album Page

    def parse_album_number(self, entry_page: WikiPage) -> int | None:
        """
        Parse the ordinal album number that indicates when the album was released by the artist, relative to other
        releases of the same type by that artist.
        """
        if intro := entry_page.intro():
            return find_ordinal(intro.raw.string)
        return None

    def _get_album_page_name(self, page: WikiPage) -> Name:  # noqa
        if (names := list(PageIntro(page).names())) and len(names) > 0:
            # log.debug(f'Using name={names[0]!r} from page intro')
            return names[0]

        infobox = page.infobox
        try:
            name_str = infobox['name'].value
        except KeyError:
            pass
        else:
            if name_str and name_str[0] == name_str[-1] == '"':
                name_str = name_str[1:-1]
            if name_str:
                # log.debug(f'Using name={name_str!r} from infobox')
                return Name.from_enclosed(name_str)

        return Name(page.title)

    def process_album_editions(self, entry: DiscographyEntry, entry_page: WikiPage) -> EditionIterator:
        log.debug(f'Processing album editions for page={entry_page}')
        try:
            name = self._get_album_page_name(entry_page)
        except Exception as e:
            raise UnexpectedPageContent(f'Error parsing page name from {entry_page=}') from e

        yield from EditionFinder(name, entry, entry_page).editions()

    def process_edition_parts(self, edition: DiscographyEntryEdition) -> Iterator[DiscographyEntryPart]:
        yield from EditionPartFinder(edition).find_parts()

    def parse_track_name(self, node: N) -> Name:
        """Parse a track name found in a list of tracks on an album page"""
        # log.debug(f'parse_track_name({node!r})')
        if isinstance(node, String):
            # log.debug(f'Processing track name from String {node=}')
            return TrackNameParser(node.value).parse_name()
        elif node.__class__ is CompoundNode:
            if has_item_types(node, String, Tag) and is_node_with(node[1], Tag, String, name='small'):
                # log.debug(f'Processing track name with small tag from {node=}')
                return TrackNameParser(node[0].value, node[1].value.value).parse_name()
            elif has_item_types(node, String, Link, String) and node[0].value == '"':
                # log.debug(f'Processing track name with String+Link+String from {node=}')
                return TrackNameParser(f'"{node[1].show}{node[2].value}').parse_name()
            elif node.only_basic and not node.find_one(Link, recurse=True):
                # log.debug(f'Processing track name with basic compound and no links from {node=}')
                # return _process_track_string(' '.join(str(n.show if isinstance(n, Link) else n.value) for n in node))
                return TrackNameParser(' '.join(node.strings())).parse_name()
            else:
                # log.debug(f'Processing track name with complex content from {node=}')
                return ComplexTrackName(node).get_name()
        else:
            log.warning(f'parse_track_name has no handling yet for: {node}', extra={'color': 9})

    def parse_single_page_track_name(self, page: WikiPage) -> Name:
        name = self._get_album_page_name(page)
        # if not isinstance(name, Name):
        #     name = Name.from_enclosed(name)

        infobox = page.infobox
        try:
            length = infobox['length'].value
        except KeyError:
            pass
        else:
            name.update(extra={'length': length})
        try:
            artist = infobox['artist']
        except KeyError:
            pass
        else:
            if isinstance(artist, CompoundNode):
                extra, remainder, artists = _process_track_extra_nodes(artist.children, 'artists', page)
                if extra:
                    name.update_extra(extra)

        return name

    # endregion

    # region Show / OST

    def parse_soundtrack_links(self, page: WikiPage) -> Iterator[Link]:
        try:
            links_section = page.sections.find('Discography')
        except (KeyError, AttributeError):
            log.debug(f'Discography section not found for {page}')
            return

        yield from links_section.find_all(Link, True)

    def parse_source_show(self, page: WikiPage) -> TVSeries | None:
        raise NotImplementedError

    # endregion


class KindieFandomParser(KpopFandomParser, site='kindie.fandom.com'):  # noqa
    pass


class ArtistDiscographyParser:
    __slots__ = ('artist_page', 'finder', 'site_parser')

    def __init__(self, artist_page: WikiPage, finder: DiscographyEntryFinder, site_parser: KpopFandomParser):
        self.artist_page: WikiPage = artist_page
        self.finder: DiscographyEntryFinder = finder
        self.site_parser: KpopFandomParser = site_parser

    def process_disco_sections(self):
        try:
            section = self.artist_page.sections.find('Discography')
        except KeyError:
            log.debug(f'No Discography section found in {self.artist_page}')
            return

        for alb_type_section, alb_type, lang in self._iter_sections(section):
            if alb_type.lower().startswith('dvd'):
                log.debug(f'Skipping {alb_type=}')
                continue

            # log.debug(f'{alb_type}: {alb_type_section.content}')
            try:
                self._process_section(alb_type_section, alb_type, lang)
            except Exception:  # noqa
                log.error(
                    f'Unexpected error processing {section=} on {self.artist_page}',
                    exc_info=True,
                    extra={'color': 'red'},
                )

    def _iter_sections(self, section: Section) -> Iterator[tuple[Section, str, str | None]]:
        if section.depth == 1:
            for alb_type, alb_type_section in section.children.items():
                yield alb_type_section, alb_type, None
        elif section.depth == 2:  # key = language, value = sub-section
            for lang, lang_section in section.children.items():
                for alb_type, alb_type_section in lang_section.children.items():
                    yield alb_type_section, alb_type, lang
        else:
            log.warning(f'Unexpected section depth={section.depth} on {self.artist_page}')

    def _process_section(self, section: Section, alb_type: str, lang: str = None):
        content = section.content
        # log.debug(f'Processing {section=} on {artist_page}:\n{content.pformat()}')
        if type(content) is CompoundNode:  # A template for splitting the discography into
            content = content[0]  # columns follows the list of albums in this section

        if not isinstance(content, List):
            try:
                raise TypeError(f'Unexpected content on {self.artist_page}: {content.pformat()}')
            except AttributeError:
                raise TypeError(f'Unexpected content on {self.artist_page}: {content!r}')

        for entry in content.iter_flat():
            self._process_entry(section, entry, alb_type, lang)

    def _process_entry(self, section: Section, entry: AnyNode, alb_type: str, lang: str):
        # log.debug(f'Processing {artist_page} {entry=}')
        if (year := self._parse_year(entry)) is None:
            return

        disco_entry = DiscoEntry(self.artist_page, entry, type_=alb_type, lang=lang, year=year)
        if isinstance(entry, CompoundNode):
            self._process_entry_node(disco_entry, entry, section, alb_type)
        elif isinstance(entry, String):
            disco_entry.title = entry.value.split('(')[0].strip(' "')
            self.finder.add_entry(disco_entry, entry)
        else:
            log.warning(f'On page={self.artist_page}, unexpected type for {entry=}')

    def _process_entry_node(self, disco_entry: DiscoEntry, entry: CompoundNode, section: Section, alb_type: str):
        links = list(entry.find_all(Link, True))
        if alb_type in {'Features', 'Collaborations'}:
            # {primary artist} - {album or single} [(with collabs)] (year)
            if isinstance(entry[1], String):
                entry_1 = entry[1].value.strip()
                if entry_1 == '-' and self.site_parser._check_type(entry, 2, Link):
                    link = entry[2]
                    links = [link]
                    disco_entry.title = link.show
                elif entry_1.startswith('-'):
                    disco_entry.title = entry_1[1:].strip(' "')
            elif isinstance(entry[1], Link):
                disco_entry.title = entry[1].show
        else:
            if isinstance(entry[0], Link):
                disco_entry.title = entry[0].show
            elif isinstance(entry[0], String):
                disco_entry.title = entry[0].value.strip(' "')

        if links:
            for link in links:
                try:
                    self.finder.add_entry_link(link, disco_entry)
                except SiteDoesNotExist:
                    log.log(19, f'Found bad {link=} on artist_page={self.artist_page!r} in {section=}')
        else:
            self.finder.add_entry(disco_entry, entry)

    def _parse_year(self, entry) -> int | None:
        # {primary artist} - {album or single} [(with collabs)] (year)
        if isinstance(entry, String):
            entry_str = entry.value
            year_str = entry_str.rsplit(maxsplit=1)[1]
        else:
            entry_str = None
            try:
                entry_str = entry[-1].value  # noqa
                year_str = entry_str.rsplit(maxsplit=1)[-1]
            except AttributeError:
                log.debug(f'Unable to parse year from {entry=} on {self.artist_page}')
                year_str = None

        try:
            return datetime.strptime(year_str, '(%Y)').year if year_str else 0
        except ValueError:
            if not (entry_str and ORD_ALBUM_MATCH(entry_str)):
                log.warning(f'Unexpected disco {entry=} on {self.artist_page}', extra={'color': 'red'})
            return None


def is_node_with(obj: AnyNode, cls: NodeTypes, val_cls: NodeTypes, **kwargs) -> bool:
    """
    Returns True if ``obj`` is a ``cls`` and it's value is a ``val_cls``.
    If keyword args are specified, the keys are treated as attribute names of ``obj``, and the values of all
    specified attributes must also match the provided values.
    """
    if not isinstance(obj, cls) or not isinstance(obj.value, val_cls):
        return False
    if kwargs:
        return all(getattr(obj, k).lower() == v for k, v in kwargs.items())
    return True


def has_item_types(node, *types) -> bool:
    if len(node) != len(types):
        return False
    return all(isinstance(item, cls) for item, cls in zip(node, types))


# region Edition Processing


class EditionFinder:
    name: Name
    entry: DiscographyEntry
    entry_page: WikiPage

    def __init__(self, name: Name, entry: DiscographyEntry, entry_page: WikiPage):
        self.name = name
        self.entry = entry
        self.entry_page = entry_page

    def get_track_list_section(self) -> Section | None:
        root = self.entry_page.sections
        for key in ('Track list', 'Tracklist'):
            try:
                return root.find_section(key, case_sensitive=False)
            except KeyError:
                pass

        return None

    @property
    def is_ost(self) -> bool:
        # This uses ._type instead of .type to avoid infinite recursion when ._type is None and DiscographyEntry.type
        # checks editions to determine the type
        return self.entry._type == DiscoEntryType.Soundtrack

    def editions(self) -> EditionIterator:
        track_list_section = self.get_track_list_section()
        # log.debug(f'On page={self.entry_page}, found {track_list_section=}')
        # log.debug(f'On page={self.entry_page}, found track_list_section={track_list_section.pformat("content")}')
        if track_list_section is None:
            # Example: https://kpop.fandom.com/wiki/Tuesday_Is_Better_Than_Monday
            yield self._edition(None, None, self.find_language(self.entry_page))
            return

        if self.is_ost and all(s.title.startswith('Part.') for s in track_list_section):
            # log.debug(f'Found {len(track_list_section)} OST parts')
            yield self._edition(track_list_section.content, '[OST Parts]', None)
            return

        try:
            track_list_section, track_section_content = dl_keys_to_subsections(track_list_section)
        except Exception:  # noqa
            orig = track_list_section.pformat('content')
            log.error(f'Error processing track list on page={self.entry_page}:\n{orig}', exc_info=True)
            return

        # log.debug(f'Found {track_section_content=}')
        # log.debug(f'Found track_section_content={track_section_content.pformat()}')
        if track_section_content:  # edition or version = None
            log.debug(f'Found base track_section_content on page={self.entry_page}')
            yield self._edition(track_section_content, None, self.find_language(track_section_content))

        discs = []
        for section in track_list_section:
            log.debug(f'Processing edition from {section=}')
            # log.debug(f'Processing edition from {section=} with content={section.pformat("content")}')
            title = section.title
            lc_title = title.lower()
            if lc_title == 'cd':  # edition or version = None
                yield self._edition(section.content, None, self.find_language(section.content))
            elif lc_title.startswith(('cd', 'disc', 'disk')):
                discs.append((section.content, self.find_language(section.content)))
            elif not lc_title.startswith('dvd'):
                edition, lang = self._process_album_version(title)
                content = section.content or section.children
                if isinstance(content, String) and section.children:
                    content = section.children
                yield self._edition(content, edition, self.find_language(section.content, lang))
            else:
                log.debug(f'Skipping edition from {section=}')

        if discs:
            # log.debug(f'For page={self.entry_page} found {discs=}')
            ed_lang = None
            if ed_langs := set(filter(None, {disc[1] for disc in discs})):
                if not (ed_lang := next(iter(ed_langs)) if len(ed_langs) == 1 else None):
                    log.debug(f'Found multiple languages for page={self.entry_page} discs: {ed_langs}')

            yield self._edition([d[0] for d in discs], None, ed_lang)  # edition or version = None

    def _process_album_version(self, title: str):
        # log.debug(f'_process_album_version({title=})')
        if title.lower() == 'pre-releases' and getattr(self.entry, '_type', None) == DiscoEntryType.Soundtrack:
            return None, None
        elif ends_with_enclosed(title):
            _name, _ver = split_enclosed(title, reverse=True, maxsplit=1)
            lc_ver = _ver.lower()
            if 'ver' in lc_ver and (lang := LANG_ABBREV_MAP.get(lc_ver.split(maxsplit=1)[0])):
                return _name, lang
        else:
            lc_title = title.lower()
            if 'ver' in lc_title and (lang := LANG_ABBREV_MAP.get(lc_title.split(maxsplit=1)[0])):
                return None, lang

        return title, None

    def _edition(self, content, edition, language) -> DiscographyEntryEdition:
        edition_obj = DiscographyEntryEdition(
            self.name,
            self.entry_page,
            self.entry,
            self.entry_type,
            self.artists,
            self.edition_date_map,
            content,
            edition,
            language,
            self.is_repackage_page,
        )
        # log.debug(f'Created edition with name={self.name} page={self.entry_page} {edition=} {language=} {content=}')
        return edition_obj

    def find_language(self, content, lang: str = None) -> OptStr:
        return find_language(content, lang, self.languages)

    @cached_property
    def is_repackage_page(self) -> bool:
        if infobox := self.entry_page.infobox:
            if alb_type := infobox.value.get('type'):
                if isinstance(alb_type, CompoundNode):  # Example: https://kpop.fandom.com/wiki/Max_%26_Match
                    alb_type = alb_type[0]
                repackage_page = alb_type.value.lower() == 'repackage'
            else:
                repackage_page = False
        else:
            repackage_page = False
        if extra := self.name.extra:
            repackage_page = repackage_page or extra.get('repackage', False)
        return repackage_page

    @cached_property
    def entry_type(self) -> DiscoEntryType:
        return DiscoEntryType.for_name(self.entry_page.categories)  # Note: 'type' is also in infobox sometimes

    @cached_property
    def artists(self) -> set[Link]:
        if not (infobox := self.entry_page.infobox):
            return set()
        try:
            all_links = self.entry_page.link_map
        except Exception as e:
            raise UnexpectedPageContent(f'Error finding artist links for entry_page={self.entry_page}') from e

        artist_links = set()
        if artists := infobox.value.get('artist'):
            if isinstance(artists, String):
                artists_str = artists.value
                if artists_str.lower() not in ('various', 'various artists'):
                    for artist in map(str.strip, artists_str.split(', ')):
                        if artist.startswith('& '):
                            artist = artist[1:].strip()
                        if artist_link := all_links.get(artist):
                            artist_links.add(artist_link)
            elif isinstance(artists, Link):
                artist_links.add(artists)
            elif isinstance(artists, ContainerNode):
                for artist in artists:
                    if isinstance(artist, Link):
                        artist_links.add(artist)
                    elif isinstance(artist, String):
                        if artist_link := all_links.get(artist.value):
                            artist_links.add(artist_link)
        return artist_links

    @cached_property
    def dates(self) -> list[date]:
        dates = []
        if (infobox := self.entry_page.infobox) and (released := infobox.value.get('released')):
            try:
                dates = [parse_date(dt_str.group(1)) for dt_str in RELEASE_DATE_PAT.finditer(released.raw.string)]
            except ValueError as e:
                log.error(f'Error parsing date on entry_page={self.entry_page!r}: {e}')
        return dates

    @cached_property
    def edition_date_map(self) -> StrDateMap:
        dates = {}
        try:
            released = self.entry_page.infobox['released']
        except (AttributeError, KeyError, TypeError):
            pass
        else:
            for edition, node in find_edition_value_pairs(released):
                if isinstance(edition, str):
                    edition = edition.casefold()
                if (value := _get_str_value(node)) and (m := RELEASE_DATE_PAT.search(value)):
                    try:
                        dates[edition] = parse_date(m.group(1))
                    except ValueError as e:
                        log.error(f'Error parsing date {value=} for {edition=} on entry_page={self.entry_page!r}: {e}')

        if None not in dates:
            try:
                dates[None] = self.dates[0]
            except IndexError:
                pass
        log.debug(f'Parsed {dates=} from page={self.entry_page}')
        return dates

    @cached_property
    def languages(self) -> set[str]:
        langs = set()
        for cat in self.entry_page.categories:
            if cat.endswith('releases'):
                for word in cat.split():
                    if lang := LANG_ABBREV_MAP.get(word):
                        langs.add(lang)
                        break
        return langs


def find_edition_value_pairs(node) -> Iterator[tuple[OptStr, N]]:
    if not isinstance(node, ContainerNode):
        yield None, node
        return

    last = None
    for ele in node:
        if ele == '<br>' or isinstance(ele, Tag) and ele.name == 'br':
            last = None
            continue
        elif not (value := _get_str_value(ele)):
            continue

        if last:
            if is_enclosed(value):
                yield value[1:-1], last
                last = None
            elif (last_value := _get_str_value(last)) and is_enclosed(last_value):
                yield last_value[1:-1], ele
                last = None
            else:
                last = ele
        else:
            try:
                a, edition, b = partition_enclosed(value)
            except ValueError:
                last = ele
            else:
                last = None
                if not (a and b) and (value := a or b):
                    yield edition, String(value)


def _get_str_value(node) -> OptStr:
    if isinstance(node, Template):
        node = node.value

    if isinstance(node, Link):
        return node.show.strip()
    elif isinstance(node, String):
        return node.value.strip()
    else:
        return None


# endregion


class EditionPartFinder:
    __slots__ = ('edition',)

    def __init__(self, edition: DiscographyEntryEdition):
        self.edition: DiscographyEntryEdition = edition

    def find_parts(self) -> Iterator[DiscographyEntryPart]:
        content, is_ost_parts = self._get_content()
        # log.debug(f'find_parts: {type(content)=}, {is_ost_parts=!s}')
        if is_ost_parts:
            yield from self._process_ost_parts(content)
        elif isinstance(content, List):
            yield DiscographyEntryPart(None, self.edition, RawTracks(content))
        elif isinstance(content, list):
            for i, track_node in enumerate(content):
                yield DiscographyEntryPart(f'CD{i + 1}', self.edition, RawTracks(track_node))
        elif isinstance(content, dict):
            yield from self._process_section_map(content)
        elif content is None and self.edition.type == DiscoEntryType.Single:
            yield DiscographyEntryPart(None, self.edition, None)
        elif isinstance(content, CompoundNode) and (lists := list(content.find_all(List))) and len(lists) == 1:  # noqa
            # Full OST with a note between th edition name and the track list (example: Vincenzo_OST)
            # log.debug('Found full OST with text before the track list')
            yield DiscographyEntryPart(None, self.edition, RawTracks(lists[0]))
        else:
            try:
                log_content, extra = content.pformat(), {'color': 'red'}
            except AttributeError:
                log_content, extra = repr(content), None

            log.warning(
                f'Unable to find parts for {self.edition!r} with type={self.edition.type}, content={log_content}',
                extra=extra,
            )

    def _get_content(self) -> tuple[CompoundNode | List | list | dict | None, bool]:
        content = self.edition._content
        # try:
        #     log.debug(f'EditionPartFinder._get_content: content={content.pformat()}')
        # except AttributeError:
        #     log.debug(f'EditionPartFinder._get_content: content={content!r}')

        if content.__class__ is CompoundNode and isinstance(content[0], List):
            """
            TODO: handle Special Track, Part.1~10, Bonus Track; Full OST
            https://kpop.fandom.com/wiki/Business_Proposal_OST

            From drama_wiki parser:

            if edition.edition == '[OST Parts]':
                yield from self._process_parts_edition_parts(edition, True)
            elif edition.edition == '[Extra Parts]':
                yield from self._process_parts_edition_parts(edition, False)
            elif edition.edition == '[Full OST]':
            """

            content_len = len(content)
            if content_len % 2 == 0 and str(content[0][0].value.raw).startswith('Part'):
                return content, True
            elif content_len == 1:
                return content[0], False
            else:
                raise ValueError(
                    f'Unexpected content for edition={self.edition!r} on page={self.edition.page.url}'
                    f' - content: {content.pformat()}'
                )
        else:
            # log.debug(f'Processing edition part content with {content.__class__=}')
            return content, False

    def _get_release_dates(self) -> list[tuple[str, DateResult]]:
        try:
            released = self.edition.page.infobox.value.get('released')
        except (KeyError, AttributeError):
            return []

        ignore = {'<br>', '<br/>'}
        try:
            strings = [
                s
                for node in released
                if (s := _get_str_value(node).strip()) and s not in ignore and (s := strip_enclosed(s).strip())
            ]
        except Exception as e:
            log.debug(f'Unable to parse strings from released box: {e}', exc_info=True)
            return []

        # log.debug(f'Infobox released={strings}')

        # Using a list of tuples for now in case a first date needs to be selected, or something like that...
        release_dates = []
        strings.reverse()
        while strings:
            try:
                release_date = parse_date(strings.pop())
            except ValueError:
                log.debug(f'Unexpected released box content: {released}')
                return []
            try:
                name_str = strings.pop()
            except IndexError:
                log.debug(f'Unexpected released box content: {released}')
            else:
                release_dates.append((name_str, release_date))

        return release_dates

    def _process_ost_parts(self, list_nodes: CompoundNode | list[List]) -> Iterator[SoundtrackPart]:
        # log.debug(f'Processing OST parts from {edition=}')
        release_dates = self._get_release_dates()
        # log.debug(f'Found {release_dates=}', extra={'color': 14})

        for node, artist_nodes, track_list in _process_ost_part_lists(list_nodes):
            # log.debug(f'_init_ost_edition_parts: {node=}, {artist_nodes=}')
            if not isinstance(node, (String, Link)):  # Likely a CompoundNode with ele 0 being a String
                node = node[0]
            name = node.show if isinstance(node, Link) else node.value
            artists = set(find_nodes(artist_nodes, Link)) if artist_nodes else None
            released = next((d for n, d in release_dates if n == name), None)
            # yield DiscographyEntryPart(name, edition, track_list)
            num = _parse_ost_part_num(name)
            if num is not None:
                name = f'Part {num}'
            # log.debug(f'_init_ost_edition_parts: {num=}, {name=}, {artists=}, {released=}')
            yield SoundtrackPart(num, name, self.edition, track_list, artist=artists, release_date=released)

    def _process_section_map(self, section_map: dict[str, Section]) -> Iterator[DiscographyEntryPart]:
        for name, section in section_map.items():
            part_content = section.content
            if part_content.__class__ is CompoundNode:  # May have a String sub-heading - see Start-Up_OST test
                for node in part_content:
                    if isinstance(node, List):
                        part_content = node
                        break

            # log.debug(f'Found disco part={name!r} with content={part_content}')
            yield DiscographyEntryPart(name, self.edition, RawTracks(part_content))


# region OST Edition Parts


def _process_ost_part_lists(list_nodes: CompoundNode | list[List]):
    i_list_nodes = iter(list_nodes)
    for list_node in i_list_nodes:
        node = list_node[0].value
        if node.__class__ is CompoundNode:
            node, *artist_nodes = node
        else:
            artist_nodes = None

        yield node, artist_nodes, next(i_list_nodes)


def _parse_ost_part_num(name) -> int | None:
    if m := PART_NUM_SEARCH(str(name).lower()):
        return int(m.group(1))
    return None


# endregion


# region Track Processing


class ComplexTrackName:
    def __init__(self, orig_node: CompoundNode):
        self.orig_node = orig_node
        self.nodes = list(orig_node)
        self.node = self.nodes.pop(0)

    def __repr__(self) -> str:
        return f'track={self.orig_node!r} node={self.node!r}'

    def _process_base_name_part_1(self) -> tuple[str, str | None]:
        node = self.node
        if isinstance(node, String):
            if node.value == '"':
                return self._process_base_name_part_1_quote()
            else:
                return self._process_base_name_part_1_str(node)
        elif isinstance(node, Link):
            remainder = None
            split_name = split_enclosed(node.show, maxsplit=1)
            # log.debug(f'split_enclosed({value!r}) => {split_name}')
            if len(split_name) == 1:
                base_name = split_name[0]
            else:
                base_name, remainder = split_name
        else:
            raise TypeError(f'Unexpected first node type for {self}')

        return base_name, remainder

    def _process_base_name_part_1_quote(self) -> tuple[str, str | None]:
        self.node = node = self.nodes.pop(0)
        if not isinstance(node, Link):
            raise ValueError(f'Unexpected second node value for {self}')

        base_name = node.show
        try:
            self.node = node = self.nodes.pop(0)
        except IndexError:
            self.node = node = String('"')  # Allow link names where the user forgot to type the end quote

        if not isinstance(node, String):
            raise TypeError(f'Unexpected third node type for {self}')

        remainder = node.value
        if remainder.count('"') == 1:
            name_part, remainder = map(str.strip, remainder.split('"', 1))
            # log.debug(f'{base_name=} {name_part=} {remainder=}')
            base_name = f'{base_name} {name_part}'
        # else:
        #     log.debug(f'{base_name=} {remainder=}')

        return base_name, remainder

    def _process_base_name_part_1_str(self, node: String) -> tuple[str, str | None]:
        remainder = None
        value = node.value
        if (
            len(self.nodes) > 1 and value.startswith('"') and has_unpaired(value)
            and isinstance(self.nodes[1], String)
            and '"' in self.nodes[1].value and has_unpaired(self.nodes[1].value)
        ):
            value = value[1:]
            self.nodes[1].value = self.nodes[1].value.replace('"', '')
        else:
            log.debug(f'nodes={self.nodes}')

        split_name = split_enclosed(value, maxsplit=1)
        # log.debug(f'split_enclosed({value!r}) => {split_name}')
        if len(split_name) == 1:
            base_name = split_name[0]
        else:
            base_name, remainder = split_name
            if prefix := next(
                (k for k in REMAINDER_ARTIST_EXTRA_TYPE_MAP if k in remainder and k != '('), None
            ):
                # log.debug(f'Found {prefix=}')
                if not remainder.startswith(prefix):
                    non_eng, extra_prefix, after = map(str.strip, remainder.partition(prefix))
                    base_name = f'{base_name} {non_eng}'
                    remainder = f'{extra_prefix} {after}'.strip()

        return base_name, remainder

    def _process_base_name_part_2(self, base_name: str, remainder: OptStr) -> tuple[str, str | None]:
        if not remainder and self.nodes:
            self.node = node = self.nodes.pop(0)
            if isinstance(node, Template) and isinstance((tmpl_value := node.value), Link):
                node = tmpl_value

            if is_node_with(node, (Tag, Template), (CompoundNode, String), name='small'):
                if isinstance((node_val := node.value), String):
                    node = node_val
                else:
                    self.nodes = list(node_val) + self.nodes
                    self.node = node = self.nodes.pop(0)
                if isinstance(node, String):
                    remainder = node.value
                else:
                    raise TypeError(f'Unexpected tag value node type for {self}')
            elif isinstance(node, String):
                remainder = node.value
            elif isinstance(node, Link):
                if m := UNCLOSED_PAREN_MATCH(base_name):
                    base_name, remainder = map(str.strip, m.groups())
                    self.nodes.insert(0, node)
                else:
                    raise TypeError(f'Unexpected node type after track name for {self}')
            elif isinstance(node, Tag) and node.name == 'ref':
                pass  # ignore references
            else:
                raise TypeError(f'Unexpected node type after track name for {self}')

        return base_name, remainder

    def _process_remainder(self, remainder: str) -> str:
        if self.nodes:
            remainder_parts = [remainder]
            for node in self.nodes:
                if is_node_with(node, Template, MappingNode, name='small'):
                    node = node.value['1']
                remainder_parts.append(str(node.show if isinstance(node, Link) else node.value))
            remainder = ' '.join(remainder_parts)
        return remainder

    def get_name(self) -> Name:
        base_name, remainder = self._process_base_name_part_1()
        # log.debug(f'Processing complex track node: {base_name=} {remainder=} nodes={self.nodes}')
        base_name, remainder = self._process_base_name_part_2(base_name, remainder)

        if remainder and (extra_type := REMAINDER_ARTIST_EXTRA_TYPE_MAP.get(remainder.lower())):
            # log.debug(f'Found {remainder=} => {extra_type=}')
            extra, remainder, artists = _process_track_extra_nodes(self.nodes, extra_type, self.orig_node)
            # log.debug(f'Found {artists=} {remainder=} {nodes=} {extra=}')
        else:
            extra = {}

        remainder = self._process_remainder(remainder or '')

        # log.debug(f'Checking {remainder=} for a duration...')
        if m := DURATION_MATCH(remainder):
            before, extra['length'], after = map(str.strip, m.groups())
            for part in filter(None, (before, after)):
                extra.update(_process_track_extras(part))

        # log.debug(f'orig_node={orig_node.pformat()} => {base_name=} + {extra=}')
        name = Name.from_enclosed(base_name, extra=extra or None)
        # log.info(f'parse_track_name has no handling yet for: {node.pformat()}', extra={'color': 10})
        return name


class TrackNameParser:
    __slots__ = ('extra', 'parts')

    def __init__(self, text: str, extra_content: str = None):
        # log.debug(f'Processing track str={text!r} with {extra_content=}')
        self.extra = dict(_process_track_extras(extra_content)) if extra_content else {}
        if m := DURATION_MATCH(text):
            text, self.extra['length'], after = map(str.strip, m.groups())
            if after:
                self.extra.update(_process_track_extras(after))

        self.parts = self._init_parts(text)

    def parse_name(self) -> Name:
        non_eng, other_parts = self._process_parts()
        name = Name(non_eng=combine_with_parens(non_eng) if non_eng else None, extra=self.extra or None)
        if other_parts:
            self._finalize(name, other_parts)
        return name

    def _init_parts(self, text: str) -> Collection[str]:
        if text.startswith('"') and not text.endswith('"') and text.count('"') == 1:
            text += '"'

        parts = split_enclosed(text)
        if (part_count := len(parts)) == 1:
            parts = split_enclosed(parts[0])
        elif part_count > 1 and text.startswith('"'):
            for part in parts[1:]:
                self.extra.update(_process_track_extras(part))
            parts = split_enclosed(parts[0])

        # log.debug(f'{parts=}')
        return parts

    def _process_parts(self) -> tuple[list[str], list[str]]:
        other_parts = []
        non_eng = []
        for part in self.parts:
            extra_type, part = _classify_track_part(part)
            if extra_type:
                if extra_type == 'version' and (current := self.extra.get(extra_type)):
                    if isinstance(current, list):
                        current.append(part)
                    else:
                        self.extra[extra_type] = [current, part]
                else:
                    self.extra[extra_type] = part
            else:
                if LangCat.contains_any(part, LangCat.non_eng_cats):
                    non_eng.append(part)
                else:
                    other_parts.append(part)

        return non_eng, other_parts

    def _finalize(self, name: Name, other_parts: list[str]):  # noqa
        if (part_count := len(other_parts)) == 1:
            name.update(_english=other_parts[0])
        elif part_count > 1:
            name_parts = []
            for part in other_parts:
                if name.has_romanization(part):
                    name.update(romanized=part)
                else:
                    name_parts.append(part)
            if name_parts:
                name.update(_english=combine_with_parens(name_parts))


def _process_track_extra_nodes(nodes: list[N], extra_type: str, source: WikiPage | N):
    root = source if isinstance(source, WikiPage) else source.root
    extra = {}
    artists = []
    remainder = None
    while nodes:
        node = nodes.pop(0)
        # log.debug(f'Processing {node=}')
        if isinstance(node, Link):
            artists.append(node)
        elif isinstance(node, String):
            if start_str := next((val for val in (')', 'duet)', 'solo)') if node.value.startswith(val)), None):
                if len(artists) == 1:
                    extra[extra_type] = artists[0]
                else:
                    extra[extra_type] = CompoundNode.from_nodes(artists, root=root, delim=' ')
                remainder = node.value[len(start_str):].strip()
                break
            elif node.value.startswith('feat.') and node.value.endswith(')'):
                if len(artists) == 1:
                    extra[extra_type] = artists[0]
                else:
                    extra[extra_type] = CompoundNode.from_nodes(artists, root=root, delim=' ')
                extra['feat'] = node.value[5:-1].strip()
                break
            elif m := VERSION_SEARCH(node.value):
                # log.debug(f'Found version match={m}')
                version_parts = [m.group(1)]
                if artists and not extra:
                    version_parts = [a.show for a in artists] + version_parts
                    artists = []
                extra['version'] = ' '.join(version_parts)
            elif node.value == '(feat.' and nodes:
                feat = []
                while nodes:
                    _node = nodes.pop(0)
                    if isinstance(_node, String) and ')' in _node.value:
                        before, _, after = map(str.strip, _node.value.partition(')'))
                        if before:
                            feat.append(String(before, root=root))
                        if after:
                            nodes.insert(0, String(after, root=root))
                        break
                    else:
                        feat.append(_node)

                if feat:
                    if len(feat) == 1:
                        extra['feat'] = feat[0]
                    else:
                        extra['feat'] = CompoundNode.from_nodes(feat, root=root, delim=' ')
            else:
                # log.debug(f'Assuming {node=} is part of artists')
                artists.append(node)
        elif is_node_with(node, Template, CompoundNode) and node.value.__class__ is CompoundNode:
            # Specifically a Template containing a Compound node, not a subclass thereof
            nodes = [*node.value.children, *nodes]  # noqa
            # _nodes = node.value.children.copy()
            # _nodes.extend(nodes)
            # nodes = _nodes
        elif node.__class__ is CompoundNode:  # Example containing a Template: https://kpop.fandom.com/wiki/Unforgiven
            nodes = [*node.children, *nodes]  # noqa
        elif isinstance(node, Template):
            nodes.insert(0, node.value)
        else:
            raise TypeError(f'Unexpected artist node type for track={source!r} {node=}')

    return extra, remainder, artists


def _classify_track_part(text: str) -> tuple[OptStr, str | bool]:
    text = text.replace(' : ', ': ')
    lc_text = text.lower()
    if lc_text.startswith(('inst.', 'instrumental')):
        return 'instrumental', True
    elif lc_text.startswith('acoustic'):
        if lc_text.endswith(('version', 'ver.')) and not lc_text[8:].strip().startswith('ver'):
            return 'version', text
        return 'acoustic', True
    elif lc_text.endswith(('version', 'ver.')):
        return 'version', text
    elif lc_text.endswith(' ost'):
        return 'album', text
    elif lc_text.startswith(('feat.', 'featuring')):
        return 'feat', text.split(maxsplit=1)[1]
    elif lc_text.endswith('remix'):
        return 'remix', text
    elif lc_text == 'extended play':
        return 'misc', text
    elif lc_text.endswith('only'):
        return 'availability', text
    else:
        return None, text


def _process_track_extras(text: str) -> Iterator[tuple[str, Any]]:
    for part in split_enclosed(text):
        extra_type, part = _classify_track_part(part)
        yield extra_type or 'misc', part


# endregion
