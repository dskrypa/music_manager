"""
:author: Doug Skrypa
"""

import logging
import re
from collections import Counter
from datetime import datetime
from typing import TYPE_CHECKING, Iterator, Optional, List, Dict, Tuple

from wiki_nodes import WikiPage, Link, String, MappingNode, Section, CompoundNode
from wiki_nodes.nodes import N, ContainerNode
from ...text.extraction import ends_with_enclosed, split_enclosed
from ...text.name import Name
from ..album import Soundtrack, SoundtrackEdition, SoundtrackPart
from ..base import EntertainmentEntity, SINGER_CATEGORIES, GROUP_CATEGORIES, TVSeries
from ..disco_entry import DiscoEntry
from .abc import WikiParser, EditionIterator

if TYPE_CHECKING:
    from ..discography import DiscographyEntryFinder

__all__ = ['DramaWikiParser']
log = logging.getLogger(__name__)

OST_PART_MATCH = re.compile(r'^(.+ OST).*?((?:Part \d+)?)$', re.IGNORECASE).match
SONG_OST_YEAR_MATCH = re.compile(r'^(.+?)\s-\s(.+?)\s\(((?:19|20)\d{2})\)$').match
YEAR_MATCH = re.compile(r'-?(.*?)\(((?:19|20)\d{2})\)$').match


class DramaWikiParser(WikiParser, site='wiki.d-addicts.com'):
    # TODO: Date for part is not being picked up
    @classmethod
    def parse_artist_name(cls, artist_page: WikiPage) -> Iterator[Name]:
        if profile := get_section_map(artist_page, 'Profile'):
            keys = ('Name', 'Real name', 'Group name')
            for key in keys:
                if value := profile.get(key):
                    parts = value.value.split(' / ')
                    if len(parts) == 2 and ends_with_enclosed(parts[1]):
                        non_eng, eng = parts
                        eng, romanized = split_enclosed(eng, maxsplit=1)
                        yield Name.from_parts((eng, non_eng), romanized=romanized)
                    else:
                        yield Name.from_parts(parts)

    @classmethod
    def parse_album_name(cls, node: N) -> Name:
        raise NotImplementedError

    @classmethod
    def parse_album_number(cls, entry_page: WikiPage) -> Optional[int]:
        raise NotImplementedError

    @classmethod
    def parse_track_name(cls, node: N) -> Name:
        if not isinstance(node, MappingNode):
            raise TypeError(f'Unexpected track node type={node.__class__.__name__!r} for {node=!r}')
        title = node['Song Title']
        extra = {'artists': node['Artist']}
        if isinstance(title, String):
            title = title.value
            if title.lower().endswith('(inst.)'):
                title = title[:-7].strip()
                extra['instrumental'] = True
            return Name.from_parts((title,), extra=extra)
        elif len(title) == 2:
            br, non_eng = title
            eng = None
        else:
            try:
                eng, br, non_eng = title
            except Exception as e:
                raise ValueError(f'Unexpected track node content for {node=!r}') from e
            else:
                eng = eng.value

        non_eng = non_eng.value
        if eng and eng.lower().endswith('(inst.)'):
            eng = eng[:-7].strip()
            extra['instrumental'] = True
        if non_eng.lower().endswith('(inst.)'):
            non_eng = non_eng[:-7].strip()
            extra['instrumental'] = True
        return Name.from_parts((eng, non_eng), extra=extra)

    @classmethod
    def parse_single_page_track_name(cls, page: WikiPage) -> Name:
        raise NotImplementedError

    @classmethod
    def process_disco_sections(cls, artist_page: WikiPage, finder: 'DiscographyEntryFinder') -> None:
        try:
            section = artist_page.sections.find('TV Show Theme Songs')
        except KeyError:
            return

        link_map = {link.show: link for link in artist_page.links()}
        # Typical format: {song title} [by {member}] - {soundtrack title} ({year})
        for entry in section.content.iter_flat():
            if isinstance(entry, String):
                if m := SONG_OST_YEAR_MATCH(entry.value):
                    song, album, year = map(str.strip, m.groups())
                    log.debug(f'Creating entry for {song=!r} {album=!r} {year=!r}')
                    disco_entry = DiscoEntry(
                        artist_page, entry, type_='Soundtrack', year=int(year), song=song, title=album
                    )
                    if link := link_map.get(album):
                        log.debug(f'  > Adding {link=!r}')
                        finder.add_entry_link(link, disco_entry)
                    else:
                        log.debug(f'  > Adding {entry=!r}')
                        finder.add_entry(disco_entry, entry)
                else:
                    log.debug(f'Unexpected String disco {entry=!r} / {entry.value!r}')
            else:
                album, song, year = None, None, None
                song_str = entry[0].value  # type: str
                if song_str.endswith('-'):
                    song = song_str[:-1].strip()
                elif song_str.endswith(' with'):
                    song = song_str[:-4].strip()

                end_str = entry[-1].value  # type: str
                if m := YEAR_MATCH(end_str):
                    album = m.group(1).strip() or None
                    year = int(m.group(2))

                log.debug(f'Creating entry for {song=!r} {album=!r} {year=!r} | {song_str=!r} {end_str=!r} {entry=!r}')
                disco_entry = DiscoEntry(artist_page, entry, type_='Soundtrack', year=year, song=song, title=album)

                if link := link_map.get(album):
                    log.debug(f'  > Adding {link=!r}')
                    finder.add_entry_link(link, disco_entry)
                else:
                    if links := list(entry.find_all(Link, True)):
                        try:
                            entities = EntertainmentEntity.from_links(links)
                        except Exception as e:
                            log.debug(f'Error retrieving EntertainmentEntities from {links=}: {e}')
                        else:
                            artist_cats = (GROUP_CATEGORIES, SINGER_CATEGORIES)
                            links = [link for link, ent in entities.items() if ent._categories not in artist_cats]

                    if not finder.add_entry_links(links, disco_entry):
                        if isinstance(entry[-2], String):
                            disco_entry.title = entry[-2].value
                        log.debug(f'  > Adding {entry=!r}')
                        finder.add_entry(disco_entry, entry)

    @classmethod
    def _process_parts_edition(
        cls, entry: 'Soundtrack', entry_page: WikiPage, ost_name: str, edition_name: str, parts: List[Section]
    ) -> SoundtrackEdition:
        log.debug(f'Found {len(parts)} {edition_name} on {entry_page=}')
        name, languages, dates, artists = None, Counter(), set(), set()
        for part in parts:  # Go thru all parts to get all languages, dates, and artists
            name = name or get_basic_info(part.content[2].as_mapping(), ost_name, languages, dates, artists)[0]

        language = max(languages, key=lambda k: languages[k], default=None)
        return SoundtrackEdition(
            name, entry_page, entry, entry._type, artists, sorted(dates), parts, f'[{edition_name}]', language
        )

    @classmethod
    def process_album_editions(cls, entry: 'Soundtrack', entry_page: WikiPage) -> EditionIterator:
        ost_parts, ost_full, ost_name, other_parts = split_sections(entry_page)
        if not (ost_full or ost_parts):
            log.warning(f'Did not find any OST content for entry={entry._basic_repr} / {entry_page!r}')

        if ost_parts:
            yield cls._process_parts_edition(entry, entry_page, ost_name, 'OST Parts', ost_parts)
        if other_parts:
            yield cls._process_parts_edition(entry, entry_page, ost_name, 'Extra Parts', other_parts)
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
                    name, entry_page, entry, entry._type, String('Various Artists'), sorted(dates), ost_full,
                    '[Full OST]', language
                )

    @classmethod
    def _process_parts_edition_parts(cls, edition: 'SoundtrackEdition', numbered: bool) -> Iterator['SoundtrackPart']:
        for i, section in enumerate(edition._content, 1):
            content = section.content
            info = get_info_map(content)
            artist = info.get('Artist')
            if part_date := info.get('Release Date'):
                rel_date = parse_date(part_date.value)
            else:
                rel_date = None

            if numbered:
                yield SoundtrackPart(i, f'Part {i}', edition, content[4], artist=artist, release_date=rel_date)
            else:
                yield SoundtrackPart(None, section.title, edition, content[4], artist=artist, release_date=rel_date)

    @classmethod
    def process_edition_parts(cls, edition: 'SoundtrackEdition') -> Iterator['SoundtrackPart']:
        if edition.edition == '[OST Parts]':
            yield from cls._process_parts_edition_parts(edition, True)
        elif edition.edition == '[Extra Parts]':
            yield from cls._process_parts_edition_parts(edition, False)
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
            log.debug(f'Unexpected {edition.edition=!r} for {edition=!r}')

    @classmethod
    def parse_group_members(cls, artist_page: WikiPage) -> Dict[str, List[str]]:
        raise NotImplementedError

    @classmethod
    def parse_member_of(cls, artist_page: WikiPage) -> Iterator[Link]:
        if trivia := get_section_map(artist_page, 'Trivia'):
            group_info = trivia.get('KPOP group')
            if isinstance(group_info, ContainerNode):
                yield from group_info.find_all(Link, True)

    @classmethod
    def parse_disco_page_entries(cls, disco_page: WikiPage, finder: 'DiscographyEntryFinder') -> None:
        raise NotImplementedError

    @classmethod
    def parse_soundtrack_links(cls, page: WikiPage) -> Iterator[Link]:
        if details := get_section_map(page, 'Details'):
            if ost_link := details.get('Original Soundtrack'):
                if isinstance(ost_link, Link):
                    yield ost_link
                else:
                    log.warning(f'An {ost_link=!r} was found on {page=!r} but it was not a Link')

    @classmethod
    def parse_source_show(cls, page: WikiPage) -> Optional[TVSeries]:
        info = get_info_map(next(iter(page.sections)).content)
        link = next(iter(info['Title'].find_all(Link, True)), None)
        return TVSeries.from_link(link) if link else None


def get_info_map(section_content):
    item = section_content[2]
    if isinstance(item[0].value, String) and item[0].value.value == 'Information':
        item = section_content[3]
    return item.as_mapping()


def parse_date(date_str: str) -> datetime:
    for dt_fmt in ('%Y-%b-%d', '%Y-%m-%d'):
        try:
            return datetime.strptime(date_str, dt_fmt)
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


def split_sections(page: WikiPage) -> Tuple[List[Section], Optional[Section], Optional[str], List[Section]]:
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
    languages: Optional[Counter] = None,
    dates: Optional[set] = None,
    artists: Optional[set] = None,
):
    languages = Counter() if languages is None else languages  # Need the None check to not replace empty provided value
    dates = set() if dates is None else dates
    artists = set() if artists is None else artists
    if langs := info.get('Language'):
        languages.update(map(str.strip, langs.value.split(',')))
    if part_date := info.get('Release Date'):
        dates.add(parse_date(part_date.value))
    if artist := info.get('Artist'):
        if isinstance(artist, CompoundNode):
            artist = String(' '.join(map(str, artist)))
        artists.add(artist)

    name = get_name(info, ost_name)
    return name, languages, dates, artists
