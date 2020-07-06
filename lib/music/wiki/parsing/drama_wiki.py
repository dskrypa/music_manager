"""
:author: Doug Skrypa
"""

import logging
import re
from typing import TYPE_CHECKING, Iterator, Optional, List, Dict

from wiki_nodes import WikiPage, Link, String, MappingNode
from wiki_nodes.nodes import N, ContainerNode
from ...text import Name
from ..album import DiscographyEntry, DiscographyEntryEdition, DiscographyEntryPart
from ..base import EntertainmentEntity, SINGER_CATEGORIES, GROUP_CATEGORIES
from ..disco_entry import DiscoEntry
from .abc import WikiParser, EditionIterator

if TYPE_CHECKING:
    from ..discography import DiscographyEntryFinder

__all__ = ['DramaWikiParser']
log = logging.getLogger(__name__)

YEAR_MATCH = re.compile(r'-?(.*?)\(((?:19|20)\d{2})\)$').match
SONG_OST_YEAR_MATCH = re.compile(r'^(.+?)\s-\s(.+?)\s\(((?:19|20)\d{2})\)$').match


class DramaWikiParser(WikiParser, site='wiki.d-addicts.com'):
    @classmethod
    def parse_artist_name(cls, artist_page: WikiPage) -> Iterator[Name]:
        if profile := get_section_map(artist_page, 'Profile'):
            keys = ('Name', 'Real name')
            for key in keys:
                if value := profile.get(key):
                    yield Name.from_parts(value.value.split(' / '))

    @classmethod
    def parse_album_name(cls, node: N) -> Name:
        raise NotImplementedError

    @classmethod
    def parse_album_number(cls, entry_page: WikiPage) -> Optional[int]:
        raise NotImplementedError

    @classmethod
    def parse_track_name(cls, node: N) -> Name:
        raise NotImplementedError

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
    def process_album_editions(cls, entry: 'DiscographyEntry', entry_page: WikiPage) -> EditionIterator:
        raise NotImplementedError

    @classmethod
    def process_edition_parts(cls, edition: 'DiscographyEntryEdition') -> Iterator['DiscographyEntryPart']:
        raise NotImplementedError

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


def get_section_map(page: WikiPage, title: str) -> Optional[MappingNode]:
    try:
        section = page.sections.find(title)
    except KeyError:
        return None
    else:
        return section.content.as_mapping()
