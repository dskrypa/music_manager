"""
:author: Doug Skrypa
"""

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Iterator, Optional

from wiki_nodes import MediaWikiClient, WikiPage, Link
from wiki_nodes.nodes import N
from ...text.name import Name

if TYPE_CHECKING:
    from ..base import TVSeries
    from ..album import DiscographyEntry, DiscographyEntryEdition, DiscographyEntryPart
    from ..discography import DiscographyEntryFinder

__all__ = ['WikiParser']
log = logging.getLogger(__name__)
EditionIterator = Iterator['DiscographyEntryEdition']


class WikiParser(ABC):
    _site_parsers = {}
    _domain_parsers = {}
    client = None

    # noinspection PyMethodOverriding
    def __init_subclass__(cls, site: str, domain: Optional[str] = None):
        WikiParser._site_parsers[site] = cls
        if domain:
            WikiParser._domain_parsers['.' + domain] = cls
        cls.client = MediaWikiClient(site)

    @classmethod
    def for_site(cls, site: str, method: Optional[str] = None) -> Optional['WikiParser']:
        if not (parser := cls._site_parsers.get(site)):
            parser = next((p for domain, p, in cls._domain_parsers.items() if site.endswith(domain)), None)

        if parser and method:
            try:
                co_names = getattr(parser, method).__code__.co_names
            except AttributeError:
                return parser
            else:
                if len(co_names) == 1 and 'NotImplementedError' in co_names:
                    return None
        return parser

    @classmethod
    @abstractmethod
    def parse_artist_name(cls, artist_page: WikiPage) -> Iterator[Name]:
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def parse_album_name(cls, node: N) -> Name:
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def parse_album_number(cls, entry_page: WikiPage) -> Optional[int]:
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def parse_track_name(cls, node: N) -> Name:
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def parse_single_page_track_name(cls, page: WikiPage) -> Name:
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def process_disco_sections(cls, artist_page: WikiPage, finder: 'DiscographyEntryFinder') -> None:
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def process_album_editions(cls, entry: 'DiscographyEntry', entry_page: WikiPage) -> EditionIterator:
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def process_edition_parts(cls, edition: 'DiscographyEntryEdition') -> Iterator['DiscographyEntryPart']:
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def parse_group_members(cls, artist_page: WikiPage) -> dict[str, list[str]]:
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def parse_member_of(cls, artist_page: WikiPage) -> Iterator[Link]:
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def parse_disco_page_entries(cls, disco_page: WikiPage, finder: 'DiscographyEntryFinder') -> None:
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def parse_soundtrack_links(cls, page: WikiPage) -> Iterator[Link]:
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def parse_source_show(cls, page: WikiPage) -> Optional['TVSeries']:
        raise NotImplementedError

    @classmethod
    def _check_type(cls, node, index, clz):
        try:
            return isinstance(node[index], clz)
        except (IndexError, KeyError, TypeError):
            return False
