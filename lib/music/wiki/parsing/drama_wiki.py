"""
:author: Doug Skrypa
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from datetime import datetime, date
from typing import TYPE_CHECKING, Iterator, Optional

from ds_tools.caching.decorators import cached_property
from wiki_nodes.nodes import N, ContainerNode, Link, String, MappingNode, Section, Tag, AnyNode
from wiki_nodes.page import WikiPage

from music.text.extraction import ends_with_enclosed, split_enclosed
from music.text.name import Name
from ..album import Soundtrack, SoundtrackEdition, SoundtrackPart
from ..base import EntertainmentEntity, SINGER_CATEGORIES, GROUP_CATEGORIES, TVSeries
from ..disco_entry import DiscoEntry
from .abc import WikiParser, EditionIterator
from .names import parse_artist

if TYPE_CHECKING:
    from ..discography import DiscographyEntryFinder
    from ..typing import StrDateMap, OptStr

__all__ = ['DramaWikiParser']
log = logging.getLogger(__name__)

OST_PART_MATCH = re.compile(r'^(.+ OST).*?((?:Part \d+)?)$', re.IGNORECASE).match
SONG_OST_YEAR_MATCH = re.compile(r'^(.+?)\s-\s(.+?)\s\(((?:19|20)\d{2})\)$').match
YEAR_MATCH = re.compile(r'-?(.*?)\(((?:19|20)\d{2})\)$').match
PRODUCER_MATCH = re.compile(r'^(.+?)\s*\(Prod(?:\.|uced)?(?:\s+by)?\s+(.+)\)$', re.IGNORECASE).match


class DramaWikiParser(WikiParser, site='wiki.d-addicts.com'):
    __slots__ = ()

    # region Artist Page

    # TODO: Date for part is not being picked up
    def parse_artist_name(self, artist_page: WikiPage) -> Iterator[Name]:
        if not (profile := get_section_map(artist_page, 'Profile')):
            return

        for key in ('Name', 'Real name', 'Group name'):
            if value := profile.get(key, case_sensitive=False):
                parts = value.value.split(' / ')
                if len(parts) == 2 and ends_with_enclosed(parts[1]):
                    non_eng, eng = parts
                    eng, romanized = split_enclosed(eng, maxsplit=1)
                    yield Name.from_parts((eng, non_eng), romanized=romanized)
                else:
                    yield Name.from_parts(parts)

    def parse_group_members(self, artist_page: WikiPage) -> dict[str, list[str]]:
        raise NotImplementedError

    def parse_member_of(self, artist_page: WikiPage) -> Iterator[Link]:
        if trivia := get_section_map(artist_page, 'Trivia'):
            if group_info := trivia.get('KPOP group'):
                yield from group_info.find_all(Link, True)

    # endregion

    # region High Level Discography

    def process_disco_sections(self, artist_page: WikiPage, finder: DiscographyEntryFinder) -> None:
        ArtistDiscographyParser(artist_page, finder, self).process_disco_sections()

    def parse_disco_page_entries(self, disco_page: WikiPage, finder: DiscographyEntryFinder) -> None:
        raise NotImplementedError

    # endregion

    # region Album Page

    def parse_album_number(self, entry_page: WikiPage) -> Optional[int]:
        raise NotImplementedError

    def parse_track_name(self, node: N) -> Name:
        if not isinstance(node, MappingNode):
            raise TypeError(f'Unexpected track node type={node.__class__.__name__!r} for {node=}')

        title = node['Song Title']
        extra = {'artists': node['Artist']}
        if isinstance(title, String):
            title, inst = strip_inst(title.value)
            if inst:
                extra['instrumental'] = True
            return Name.from_parts((title,), extra=extra)

        if not isinstance(title, ContainerNode):
            raise ValueError(f'Unexpected track node {title=} content for {node=}')

        eng, non_eng, inst = split_title(title)
        if inst:
            extra['instrumental'] = True

        eng, eng_producer = split_producer(eng)
        non_eng, non_eng_producer = split_producer(non_eng)
        if eng_producer and non_eng_producer:
            extra['producer'] = Name.from_parts((eng_producer, non_eng_producer))
        elif producer_str := eng_producer or non_eng_producer:
            extra['producer'] = parse_artist(producer_str, node)

        return Name.from_parts((eng, non_eng), extra=extra)

    def parse_single_page_track_name(self, page: WikiPage) -> Name:
        raise NotImplementedError

    def _process_parts_edition(  # noqa
        self, entry: Soundtrack, entry_page: WikiPage, ost_name: str, edition_name: str, parts: list[Section]
    ) -> SoundtrackEdition:
        log.debug(f'Found {len(parts)} {edition_name} on {entry_page=}')
        name, languages, dates, artists = None, Counter(), {}, set()
        ed_name = f'[{edition_name}]'
        for part in parts:  # Go thru all parts to get all languages, dates, and artists
            name = name or get_basic_info(part.content[2].as_mapping(), ost_name, languages, dates, artists, ed_name)[0]

        language = max(languages, key=lambda k: languages[k], default=None)
        return SoundtrackEdition(name, entry_page, entry, entry._type, artists, dates, parts, ed_name, language)

    def process_album_editions(self, entry: Soundtrack, entry_page: WikiPage) -> EditionIterator:
        ost_parts, ost_full, ost_name, other_parts = split_sections(entry_page)
        if not (ost_full or ost_parts):
            log.warning(f'Did not find any OST content for entry={entry._basic_repr} / {entry_page!r}')

        if ost_parts:
            yield self._process_parts_edition(entry, entry_page, ost_name, 'OST Parts', ost_parts)
        # TODO: https://wiki.d-addicts.com/A_Girl_Who_Sees_Smells_OST#A_Girl_Who_Sees_Smells_OST_.28Special_Edition.29
        #  - the special edition doesn't show up as a choice in the picker
        if other_parts:
            yield self._process_parts_edition(entry, entry_page, ost_name, 'Extra Parts', other_parts)
        if ost_full:
            log.debug(f'Found full OST section on {entry_page=}')
            try:
                name, languages, dates, artists = get_basic_info(get_info_map(ost_full.content), ost_name)
            except Exception as e:
                log.error(
                    f'Error extracting basic info from full OST section on {entry_page}: {e} - section={ost_full}',
                    extra={'color': 9}
                )
            else:
                language = max(languages, key=lambda k: languages[k], default=None)
                yield SoundtrackEdition(
                    name, entry_page, entry, entry._type, String('Various Artists'), dates, ost_full,
                    '[Full OST]', language
                )

    def _process_parts_edition_parts(self, edition: SoundtrackEdition, numbered: bool) -> Iterator[SoundtrackPart]:  # noqa
        for i, section in enumerate(edition._content, 1):
            content = section.content
            info = get_info_map(content)
            artist = info.get('Artist')
            if part_date := info.get('Release Date'):
                rel_date = parse_date(part_date.value)
            else:
                rel_date = None

            # log.debug(f'_process_parts_edition_parts: [{i}] {artist=}, {rel_date=}')
            if numbered:
                yield SoundtrackPart(i, f'Part {i}', edition, content[4], artist=artist, release_date=rel_date)
            else:
                yield SoundtrackPart(None, section.title, edition, content[4], artist=artist, release_date=rel_date)

    def process_edition_parts(self, edition: SoundtrackEdition) -> Iterator[SoundtrackPart]:
        if edition.edition == '[OST Parts]':
            yield from self._process_parts_edition_parts(edition, True)
        elif edition.edition == '[Extra Parts]':
            yield from self._process_parts_edition_parts(edition, False)
        elif edition.edition == '[Full OST]':
            section = edition._content
            content = section.content
            info = get_info_map(content)
            if part_date := info.get('Release Date'):
                release_date = parse_date(part_date.value)
            else:
                release_date = None
            artist = info.get('Artist')
            try:
                track_table = content[4]
            except IndexError:
                for i, disk_section in enumerate(section, 1):
                    yield SoundtrackPart(
                        None, None, edition, disk_section.content[1], artist=artist, disc=i, release_date=release_date
                    )
            else:
                yield SoundtrackPart(None, None, edition, track_table, artist=artist, release_date=release_date)
        else:
            log.debug(f'Unexpected {edition.edition=} for {edition=}')

    # endregion

    # region Show / OST

    def parse_soundtrack_links(self, page: WikiPage) -> Iterator[Link]:
        if details := get_section_map(page, 'Details'):
            if ost_link := details.get('Original Soundtrack', case_sensitive=False):
                if isinstance(ost_link, Link):
                    yield ost_link
                else:
                    log.warning(f'An {ost_link=} was found on {page=} but it was not a Link')

    def parse_source_show(self, page: WikiPage) -> Optional[TVSeries]:
        info = get_info_map(next(iter(page.sections)).content)
        link = next(iter(info['Title'].find_all(Link, True)), None)
        return TVSeries.from_link(link) if link else None

    # endregion


class ArtistDiscographyParser:
    def __init__(self, artist_page: WikiPage, finder: DiscographyEntryFinder, site_parser: DramaWikiParser):
        self.artist_page: WikiPage = artist_page
        self.finder: DiscographyEntryFinder = finder
        self.site_parser: DramaWikiParser = site_parser

    @cached_property
    def link_map(self):
        return {link.show: link for link in self.artist_page.links()}

    def process_disco_sections(self):
        try:
            section = self.artist_page.sections.find('TV Show Theme Songs')
        except KeyError:
            log.debug(f'No Discography section found in {self.artist_page}')
            return

        # Typical format: {song title} [by {member}] - {soundtrack title} ({year})
        for entry in section.content.iter_flat():
            if isinstance(entry, String):
                self._process_string_entry(entry)
            else:
                self._process_other_entry(entry)

    def _process_string_entry(self, entry: String):
        if m := SONG_OST_YEAR_MATCH(entry.value):
            song, album, year = map(str.strip, m.groups())
            log.debug(f'Creating entry for {song=} {album=} {year=}')
            disco_entry = DiscoEntry(
                self.artist_page, entry, type_='Soundtrack', year=int(year), song=song, title=album
            )
            if link := self.link_map.get(album):
                log.debug(f'  > Adding {link=}')
                self.finder.add_entry_link(link, disco_entry)
            else:
                log.debug(f'  > Adding {entry=}')
                self.finder.add_entry(disco_entry, entry)
        else:
            log.debug(f'Unexpected String disco {entry=} / {entry.value!r}')

    def _process_other_entry(self, entry: AnyNode):
        song_str, song = self._parse_song(entry)

        end_str = entry[-1].value  # type: str
        if m := YEAR_MATCH(end_str):
            album = m.group(1).strip() or None
            year = int(m.group(2))
        else:
            album = year = None

        log.debug(f'Creating entry for {song=} {album=} {year=} | {song_str=} {end_str=} {entry=}')
        disco_entry = DiscoEntry(self.artist_page, entry, type_='Soundtrack', year=year, song=song, title=album)

        if link := self.link_map.get(album):
            log.debug(f'  > Adding {link=}')
            self.finder.add_entry_link(link, disco_entry)
            return

        if links := list(entry.find_all(Link, True)):
            try:
                entities = EntertainmentEntity.from_links(links)
            except Exception as e:
                log.debug(f'Error retrieving EntertainmentEntities from {links=}: {e}')
            else:
                artist_cats = (GROUP_CATEGORIES, SINGER_CATEGORIES)
                links = [link for link, ent in entities.items() if ent._categories not in artist_cats]

        if not self.finder.add_entry_links(links, disco_entry):
            if isinstance(entry[-2], String):
                disco_entry.title = entry[-2].value
            log.debug(f'  > Adding {entry=}')
            self.finder.add_entry(disco_entry, entry)

    def _parse_song(self, entry: AnyNode) -> tuple[str, str | None]:
        song_str = entry[0].value  # type: str
        if song_str.endswith('-'):
            song = song_str[:-1].strip()
        elif song_str.endswith(' with'):
            song = song_str[:-4].strip()
        else:
            song = None

        return song_str, song


def get_info_map(section_content):
    item = section_content[2]
    if isinstance(item[0].value, String) and item[0].value.value == 'Information':
        item = section_content[3]
    return item.as_mapping()


def parse_date(date_str: str) -> date:
    for dt_fmt in ('%Y-%b-%d', '%Y-%m-%d'):
        try:
            return datetime.strptime(date_str, dt_fmt).date()
        except ValueError:
            pass
    raise ValueError(f'Unable to parse {date_str=} using any configured patterns')


def get_section_map(page: WikiPage, title: str) -> Optional[MappingNode]:
    try:
        section = page.sections.find(title)
    except KeyError:
        return None
    else:
        return section.content.as_mapping()


def split_sections(page: WikiPage) -> tuple[list[Section], Optional[Section], Optional[str], list[Section]]:
    ost_full = None
    ost_parts = []
    other_parts = []
    ost_name = None
    for section in page.sections:
        # log.debug(f'Splitting title={section.title!r} ({ost_name=})')
        if m := OST_PART_MATCH(section.title):
            _ost_name, part_name = m.groups()
            ost_name = ost_name or _ost_name
            if part_name:
                ost_parts.append(section)
            elif section.title in ('Unofficial OST', 'Unoffical OST'):  # typo intentional
                other_parts.append(section)
            else:
                ost_full = section
        else:
            break

    return ost_parts, ost_full, ost_name, other_parts


def get_name(info: MappingNode, ost_name: Optional[str]) -> Name:
    title_node = info['Title']
    non_eng_title = title_node[0].value  # type: str  # TODO: handle other cases
    # log.debug(f'Processing {non_eng_title=}')
    if non_eng_title.endswith('/'):
        non_eng_title = non_eng_title[:-1].strip()
        # log.debug(f'  - updated to {non_eng_title=}')

    if m := OST_PART_MATCH(non_eng_title):
        non_eng_name = m.group(1)
    elif len(title_node) == 2 and isinstance(title_node[1], Link):
        ost_name = title_node[1].show
        non_eng_name = non_eng_title
        # log.debug(f'  -> Using new {ost_name=} with {non_eng_name=}')
    else:
        raise ValueError(f'Unexpected format for part name={non_eng_title!r} in {ost_name=}')

    return Name.from_parts((ost_name, non_eng_name))


def get_basic_info(
    info: MappingNode,
    ost_name: Optional[str],
    languages: Counter = None,
    dates: StrDateMap = None,
    artists: set[N] = None,
    ed_name: str = None,
):
    languages = Counter() if languages is None else languages  # Need the None check to not replace empty provided value
    if dates is None:
        dates = {}
    if artists is None:
        artists = set()
    if langs := info.get('Language'):
        languages.update(map(str.strip, langs.value.split(',')))
    if artist := info.get('Artist'):
        if isinstance(artist, ContainerNode):
            artist = String(' '.join(map(str, artist)))
        artists.add(artist)

    name = get_name(info, ost_name)
    if part_date := info.get('Release Date'):
        dates[ed_name] = part_date = parse_date(part_date.value)
        dates.setdefault(None, part_date)

    return name, languages, dates, artists


def split_title(title: ContainerNode) -> tuple[str, str, bool]:
    eng_parts = []
    non_eng_parts = []

    found_br = False
    for node in title:
        if isinstance(node, Tag) and node.name == 'br':
            found_br = True
        elif found_br:
            non_eng_parts.extend(node.strings())
        else:
            eng_parts.extend(node.strings())

    eng, eng_inst = strip_inst(' '.join(eng_parts))
    non_eng, non_eng_inst = strip_inst(' '.join(non_eng_parts))
    return eng, non_eng, eng_inst or non_eng_inst


def strip_inst(title: OptStr) -> tuple[OptStr, bool]:
    if title and title.lower().endswith('(inst.)'):
        title = title[:-7].strip()
        return title, True
    return title, False


def split_producer(title: OptStr) -> tuple[OptStr, OptStr]:
    if title and (m := PRODUCER_MATCH(title)):
        title, producer = m.groups()
        return title.strip(), producer.strip()

    return title, None
