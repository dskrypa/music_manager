"""
:author: Doug Skrypa
"""

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Iterator, Optional, List, Dict

from wiki_nodes import WikiPage, Link, String
from wiki_nodes.nodes import N
from ...text import Name
from ..album import DiscographyEntry, DiscographyEntryEdition, DiscographyEntryPart
from ..disco_entry import DiscoEntry
from .abc import WikiParser, EditionIterator

if TYPE_CHECKING:
    from ..discography import DiscographyEntryFinder

__all__ = ['DramaWikiParser']
log = logging.getLogger(__name__)


class DramaWikiParser(WikiParser, site='wiki.d-addicts.com'):
    @classmethod
    def parse_artist_name(cls, artist_page: WikiPage) -> Iterator[Name]:
        raise NotImplementedError

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
    def process_disco_sections(cls, artist_page: WikiPage, finder: 'DiscographyEntryFinder') -> None:
        try:
            section = artist_page.sections.find('TV Show Theme Songs')
        except KeyError:
            return
        # Typical format: {song title} [by {member}] - {soundtrack title} ({year})
        for entry in section.content.iter_flat():
            year = datetime.strptime(entry[-1].value.split()[-1], '(%Y)').year
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
