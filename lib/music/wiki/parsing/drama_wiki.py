"""
:author: Doug Skrypa
"""

import logging
import re
from typing import TYPE_CHECKING, Iterator, Optional, List, Dict

from wiki_nodes import WikiPage, Link, String, CompoundNode
from wiki_nodes.nodes import N, ContainerNode
from ...text import Name
from ..album import DiscographyEntry, DiscographyEntryEdition, DiscographyEntryPart
from ..disco_entry import DiscoEntry
from .abc import WikiParser, EditionIterator

if TYPE_CHECKING:
    from ..discography import DiscographyEntryFinder

__all__ = ['DramaWikiParser']
log = logging.getLogger(__name__)
YEAR_SEARCH = re.compile(r'(?<!\d)((?:19|20)\d{2})(?!\d)').search
SONG_OST_YEAR_MATCH = re.compile(r'^(.+?)\s-\s(.+?)\s\(((?:19|20)\d{2})\)$').match


class DramaWikiParser(WikiParser, site='wiki.d-addicts.com'):
    @classmethod
    def parse_artist_name(cls, artist_page: WikiPage) -> Iterator[Name]:
        try:
            section = artist_page.sections.find('Profile')
        except KeyError:
            pass
        else:
            profile = section.content.as_mapping()
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
                    title, album, year = map(str.strip, m.groups())
                    disco_entry = DiscoEntry(artist_page, entry, type_='Soundtrack', year=int(year), title=title)
                    if link := link_map.get(album):
                        finder.add_entry_link(link, disco_entry)
                    else:
                        finder.add_entry(disco_entry, entry)
                else:
                    log.debug(f'Unexpected String disco {entry=!r} / {entry.value!r}')
            else:
                entry_str = entry[-1].value
                year = int(m.group(1)) if (m := YEAR_SEARCH(entry_str.split()[-1])) else None
                disco_entry = DiscoEntry(artist_page, entry, type_='Soundtrack', year=year)
                links = list(entry.find_all(Link, True))
                if not finder.add_entry_links(links, disco_entry):
                    if isinstance(entry[-2], String):
                        disco_entry.title = entry[-2].value
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
        raise NotImplementedError

    @classmethod
    def parse_disco_page_entries(cls, disco_page: WikiPage, finder: 'DiscographyEntryFinder') -> None:
        raise NotImplementedError
