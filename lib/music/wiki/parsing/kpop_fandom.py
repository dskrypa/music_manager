"""
:author: Doug Skrypa
"""

import logging
import re
from datetime import datetime, date
from traceback import format_exc
from typing import TYPE_CHECKING, Iterator, Optional, List, Dict, Set, Union

from wiki_nodes import (
    WikiPage, Node, Link, String, CompoundNode, Section, Table, MappingNode, TableSeparator, Template, List as WikiList
)
from ...common import DiscoEntryType
from ...text import Name
from ..album import DiscographyEntry, DiscographyEntryEdition
from ..base import EntertainmentEntity, GROUP_CATEGORIES
from ..disco_entry import DiscoEntry
from .abc import WikiParser, EditionIterator
from .utils import artist_name_from_intro, find_ordinal, get_artist_title, LANG_ABBREV_MAP, find_language

if TYPE_CHECKING:
    from ..discography import DiscographyEntryFinder

__all__ = ['KpopFandomParser']
log = logging.getLogger(__name__)

MEMBER_TYPE_SECTIONS = {'former': 'Former', 'inactive': 'Inactive', 'sub_units': 'Sub-Units'}
RELEASE_DATE_FINDITER = re.compile(r'([a-z]+ \d+, \d{4})', re.IGNORECASE).finditer


class KpopFandomParser(WikiParser, site='kpop.fandom.com'):
    @classmethod
    def parse_artist_name(cls, artist_page: WikiPage) -> Iterator[Name]:
        yield from artist_name_from_intro(artist_page)
        if _infobox := artist_page.infobox:
            log.debug(f'Found infobox for {artist_page}')
            infobox = _infobox.value
            if birth_name := infobox.get('birth_name'):
                if isinstance(birth_name, String):
                    yield Name.from_enclosed(birth_name.value)
                elif isinstance(birth_name, CompoundNode):
                    for line in birth_name:
                        if isinstance(line, String):
                            yield Name.from_enclosed(line.value)
                else:
                    raise ValueError(f'Unexpected format for birth_name={birth_name.pformat()}')
            else:
                eng = eng.value if (eng := infobox.get('name')) else None
                non_eng_map = {
                    script: node.value for script in ('hangul', 'hanja', 'hiragana', 'kanji')
                    if (node := infobox.get(script))
                }
                if eng or non_eng_map:
                    non_eng = non_eng_map.pop('hangul', None) or non_eng_map.popitem()[1] if non_eng_map else None
                    yield Name(eng, non_eng, versions=[Name(eng, val) for val in non_eng_map.values()])
        else:
            log.debug(f'No infobox found for {artist_page}')

    @classmethod
    def parse_album_name(cls, node: Node) -> Name:
        raise NotImplementedError

    @classmethod
    def parse_album_number(cls, entry_page: WikiPage) -> Optional[int]:
        if intro := entry_page.intro:
            return find_ordinal(intro.raw.string)
        return None

    @classmethod
    def parse_track_name(cls, node: Node) -> Name:
        raise NotImplementedError

    @classmethod
    def process_disco_sections(cls, artist_page: WikiPage, finder: 'DiscographyEntryFinder') -> None:
        try:
            section = artist_page.sections.find('Discography')
        except KeyError:
            return

        if section.depth == 1:
            for alb_type, alb_type_section in section.children.items():
                try:
                    cls._process_disco_section(artist_page, finder, alb_type_section, alb_type)
                except Exception as e:
                    msg = f'Unexpected error processing section={section}: {format_exc()}'
                    log.error(msg, extra={'color': 'red'})
        elif section.depth == 2:  # key = language, value = sub-section
            for lang, lang_section in section.children.items():
                for alb_type, alb_type_section in lang_section.children.items():
                    # log.debug(f'{at_section}: {at_section.content}')
                    try:
                        cls._process_disco_section(artist_page, finder, alb_type_section, alb_type, lang)
                    except Exception as e:
                        msg = f'Unexpected error processing section={section}: {format_exc()}'
                        log.error(msg, extra={'color': 'red'})
        else:
            log.warning(f'Unexpected section depth: {section.depth}')

    @classmethod
    def _process_disco_section(
            cls, artist_page: WikiPage, finder: 'DiscographyEntryFinder', section: Section, alb_type: str,
            lang: Optional[str] = None
    ) -> None:
        content = section.content
        if type(content) is CompoundNode:  # A template for splitting the discography into
            content = content[0]  # columns follows the list of albums in this section
        for entry in content.iter_flat():
            # {primary artist} - {album or single} [(with collabs)] (year)
            if isinstance(entry, String):
                year_str = entry.value.rsplit(maxsplit=1)[1]
            else:
                year_str = entry[-1].value.split()[-1]

            year = datetime.strptime(year_str, '(%Y)').year
            disco_entry = DiscoEntry(artist_page, entry, type_=alb_type, lang=lang, year=year)

            if isinstance(entry, CompoundNode):
                links = list(entry.find_all(Link, True))
                if alb_type == 'Features':
                    # {primary artist} - {album or single} [(with collabs)] (year)
                    if isinstance(entry[1], String):
                        entry_1 = entry[1].value.strip()
                        if entry_1 == '-' and cls._check_type(entry, 2, Link):
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
                        finder.add_entry_link(link, disco_entry)
                else:
                    finder.add_entry(disco_entry, entry)
            elif isinstance(entry, String):
                disco_entry.title = entry.value.split('(')[0].strip(' "')
                finder.add_entry(disco_entry, entry)
            else:
                log.warning(f'On page={artist_page}, unexpected type for entry={entry!r}')

    @classmethod
    def process_album_editions(cls, entry: 'DiscographyEntry', entry_page: WikiPage) -> EditionIterator:
        infobox = entry_page.infobox
        name = infobox['name'].value
        repackage_page = (alb_type := infobox.value.get('type')) and alb_type.value.lower() == 'repackage'
        entry_type = DiscoEntryType.for_name(entry_page.categories)     # Note: 'type' is also in infobox sometimes
        artists = cls._find_artist_links(infobox, entry_page)
        dates = cls._find_release_dates(infobox)

        langs = set()
        for cat in entry_page.categories:
            if cat.endswith('releases'):
                for word in cat.split():
                    if lang := LANG_ABBREV_MAP.get(word):
                        langs.add(lang)
                        break

        if track_list_section := entry_page.sections.find('Track list', None):
            track_section_content = track_list_section.processed(False, False, False, False, True)
            if track_section_content:
                yield DiscographyEntryEdition(  # edition or version = None
                    name, entry_page, entry, entry_type, artists, dates, track_section_content, None,
                    find_language(track_section_content, None, langs), repackage_page
                )
            for section in track_list_section:
                pass
                # yield cls._process_album_edition(entry, entry_page, section.content, section.title)
        else:
            # May be a single with only one track
            pass

    @classmethod
    def _find_release_dates(cls, infobox: Template) -> List[date]:
        dates = []
        if released := infobox.value.get('released'):
            for dt_str in RELEASE_DATE_FINDITER(released.raw.string):
                dates.append(datetime.strptime(dt_str.group(1), '%B %d, %Y').date())
        return dates

    @classmethod
    def _find_artist_links(cls, infobox: Template, entry_page: WikiPage) -> Set[Link]:
        all_links = {link.title: link for link in entry_page.find_all(Link)}
        artist_links = set()
        if artists := infobox.value.get('artist'):
            if isinstance(artists, String):
                artists_str = artists.value
                if artists_str.lower() not in ('various', 'various artists'):
                    for artist in artists_str.split(', '):
                        artist = artist.strip()
                        if artist.startswith('& '):
                            artist = artist[1:].strip()
                        if artist_link := all_links.get(artist):
                            artist_links.add(artist_link)
            elif isinstance(artists, Link):
                artist_links.add(artists)
            elif isinstance(artists, CompoundNode):
                for artist in artists:
                    if isinstance(artist, Link):
                        artist_links.add(artist)
                    elif isinstance(artist, String):
                        if artist_link := all_links.get(artist.value):
                            artist_links.add(artist_link)
        return artist_links

    @classmethod
    def parse_group_members(cls, artist_page: WikiPage) -> Dict[str, List[str]]:
        try:
            members_section = artist_page.sections.find('Members')
        except (KeyError, AttributeError):
            log.debug(f'Members section not found for {artist_page}')
            return {}

        members = {'current': []}
        section = 'current'
        if isinstance(members_section.content, Table):
            for row in members_section.content:
                if isinstance(row, MappingNode) and (title := get_artist_title(row['Name'], artist_page)):
                    # noinspection PyUnboundLocalVariable
                    members[section].append(title)
                elif isinstance(row, TableSeparator) and row.value and isinstance(row.value, String):
                    section = row.value.value
                    members[section] = []
        else:
            for member in members_section.content.iter_flat():
                if title := get_artist_title(member, artist_page):
                    members['current'].append(title)

        if sub_units := artist_page.sections.find('Sub-units', None):
            members['sub_units'] = []
            for sub_unit in sub_units.content.iter_flat():
                if title := get_artist_title(sub_unit, artist_page):
                    members['sub_units'].append(title)

        return members

    @classmethod
    def parse_member_of(cls, artist_page: WikiPage) -> Iterator[Link]:
        if intro := artist_page.intro:
            for link, entity in EntertainmentEntity.from_links(intro.find_all(Link, recurse=True)).items():
                # noinspection PyUnresolvedReferences
                if entity._categories == GROUP_CATEGORIES and (members := entity.members):
                    # noinspection PyUnboundLocalVariable
                    if any(artist_page == page for m in members for page in m.pages):
                        yield link

    @classmethod
    def parse_disco_page_entries(cls, disco_page: WikiPage, finder: 'DiscographyEntryFinder') -> None:
        # This site does not use discography pages.
        return None
