"""
:author: Doug Skrypa
"""

import logging
from datetime import datetime
from traceback import format_exc
from typing import TYPE_CHECKING, Iterator, Optional, List, Dict

from wiki_nodes import WikiPage, Node, Link, String, CompoundNode, Section, Table, MappingNode, TableSeparator
from ...text import Name
from ..album import DiscographyEntry
from ..base import EntertainmentEntity, GROUP_CATEGORIES
from ..disco_entry import DiscoEntry
from .abc import WikiParser, EditionIterator
from .utils import artist_name_from_intro, find_ordinal, get_artist_title

if TYPE_CHECKING:
    from ..discography import DiscographyEntryFinder

__all__ = ['KpopFandomParser']
log = logging.getLogger(__name__)

MEMBER_TYPE_SECTIONS = {'former': 'Former', 'inactive': 'Inactive', 'sub_units': 'Sub-Units'}


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
        raise NotImplementedError

    @classmethod
    def parse_group_members(cls, entry_page: WikiPage) -> Dict[str, List[str]]:
        try:
            members_section = entry_page.sections.find('Members')
        except (KeyError, AttributeError):
            log.debug(f'Members section not found for {entry_page}')
            return {}

        members = {'current': []}
        section = 'current'
        if isinstance(members_section.content, Table):
            for row in members_section.content:
                if isinstance(row, MappingNode) and (title := get_artist_title(row['Name'], entry_page)):
                    # noinspection PyUnboundLocalVariable
                    members[section].append(title)
                elif isinstance(row, TableSeparator) and row.value and isinstance(row.value, String):
                    section = row.value.value
                    members[section] = []
        else:
            for member in members_section.content.iter_flat():
                if title := get_artist_title(member, entry_page):
                    members['current'].append(title)

        if sub_units := entry_page.sections.find('Sub-units', None):
            members['sub_units'] = []
            for sub_unit in sub_units.content.iter_flat():
                if title := get_artist_title(sub_unit, entry_page):
                    members['sub_units'].append(title)

        return members

    @classmethod
    def parse_member_of(cls, entry_page: WikiPage) -> Iterator[Link]:
        if intro := entry_page.intro:
            for link, entity in EntertainmentEntity.from_links(intro.find_all(Link, recurse=True)).items():
                # noinspection PyUnresolvedReferences
                if entity._categories == GROUP_CATEGORIES and (members := entity.members):
                    # noinspection PyUnboundLocalVariable
                    if any(entry_page == page for m in members for page in m.pages):
                        yield link

    @classmethod
    def parse_disco_page_entries(cls, disco_page: WikiPage, finder: 'DiscographyEntryFinder') -> None:
        # This site does not use discography pages.
        return None
