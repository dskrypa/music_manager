"""
:author: Doug Skrypa
"""

import logging
from typing import TYPE_CHECKING, Iterator, Optional, List, Dict

from wiki_nodes import WikiPage, Node, Template, Link
from ...text import Name
from ..album import DiscographyEntry
from ..discography import Discography
from .abc import WikiParser, EditionIterator

if TYPE_CHECKING:
    from ..discography import DiscographyEntryFinder

__all__ = ['WikipediaParser']
log = logging.getLogger(__name__)


class WikipediaParser(WikiParser, site='en.wikipedia.org'):
    @classmethod
    def parse_artist_name(cls, artist_page: WikiPage) -> Iterator[Name]:
        raise NotImplementedError

    @classmethod
    def parse_album_name(cls, node: Node) -> Name:
        raise NotImplementedError

    @classmethod
    def parse_album_number(cls, entry_page: WikiPage) -> Optional[int]:
        raise NotImplementedError

    @classmethod
    def parse_track_name(cls, node: Node) -> Name:
        raise NotImplementedError

    @classmethod
    def process_disco_sections(cls, artist_page: WikiPage, finder: 'DiscographyEntryFinder') -> None:
        try:
            section = artist_page.sections.find('Discography')
        except KeyError:
            log.debug(f'No discography section found for {artist_page}')
            return
        try:
            disco_page_link_tmpl = section.content[0]
        except Exception as e:
            log.debug(f'Unexpected error finding the discography page link on {artist_page}: {e}')
            return

        if isinstance(disco_page_link_tmpl, Template) and disco_page_link_tmpl.name.lower() == 'main':
            try:
                disco_page_title = disco_page_link_tmpl.value[0].value
            except Exception as e:
                log.debug(f'Unexpected error finding the discography page link on {artist_page}: {e}')
            else:
                disco_entity = Discography.from_page(cls.client.get_page(disco_page_title))
                disco_entity._process_entries(finder)
        else:
            log.debug(f'Unexpected discography section format on {artist_page}')

    @classmethod
    def process_album_editions(cls, entry: 'DiscographyEntry', entry_page: WikiPage) -> EditionIterator:
        raise NotImplementedError

    @classmethod
    def parse_group_members(cls, entry_page: WikiPage) -> Dict[str, List[str]]:
        raise NotImplementedError

    @classmethod
    def parse_member_of(cls, entry_page: WikiPage) -> Iterator[Link]:
        raise NotImplementedError
