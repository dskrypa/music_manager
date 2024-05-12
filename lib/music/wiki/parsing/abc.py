"""
:author: Doug Skrypa
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Iterator, Optional

from wiki_nodes import MediaWikiClient, WikiPage, Link
from wiki_nodes.nodes import N

from music.text.name import Name

if TYPE_CHECKING:
    from ..base import TVSeries
    from ..album import DiscographyEntry, DiscographyEntryEdition, DiscographyEntryPart
    from ..discography import DiscographyEntryFinder

__all__ = ['WikiParser']
log = logging.getLogger(__name__)
EditionIterator = Iterator['DiscographyEntryEdition']


class WikiParser(ABC):
    __slots__ = ()
    _site_parsers = {}
    _domain_parsers = {}
    client = None

    def __init_subclass__(cls, site: str, domain: Optional[str] = None, **kwargs):  # noqa
        super().__init_subclass__(**kwargs)
        cls._site_parsers[site] = cls
        if domain:
            cls._domain_parsers['.' + domain] = cls
        cls.client = MediaWikiClient(site)

    @classmethod
    def for_site(cls, site: str, method: Optional[str] = None) -> Optional[WikiParser]:
        if not (parser := cls._site_parsers.get(site)):
            parser = next((p for domain, p, in cls._domain_parsers.items() if site.endswith(domain)), None)

        if parser:
            parser = parser()

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
    def get_sites(cls) -> list[str]:
        return sorted(cls._site_parsers)

    # region Artist Page

    @abstractmethod
    def parse_artist_name(self, artist_page: WikiPage) -> Iterator[Name]:
        raise NotImplementedError

    @abstractmethod
    def parse_group_members(self, artist_page: WikiPage) -> dict[str, list[str]]:
        raise NotImplementedError

    @abstractmethod
    def parse_member_of(self, artist_page: WikiPage) -> Iterator[Link]:
        raise NotImplementedError

    # endregion

    # region High Level Discography

    @abstractmethod
    def process_disco_sections(self, artist_page: WikiPage, finder: DiscographyEntryFinder) -> None:
        raise NotImplementedError

    @abstractmethod
    def parse_disco_page_entries(self, disco_page: WikiPage, finder: DiscographyEntryFinder) -> None:
        raise NotImplementedError

    # endregion

    # region Album Page

    @abstractmethod
    def parse_album_number(self, entry_page: WikiPage) -> Optional[int]:
        """
        Parse the ordinal album number that indicates when the album was released by the artist, relative to other
        releases of the same type by that artist.
        """
        raise NotImplementedError

    @abstractmethod
    def parse_track_name(self, node: N) -> Name:
        """Parse a track name found in a list of tracks on an album page"""
        raise NotImplementedError

    @abstractmethod
    def parse_single_page_track_name(self, page: WikiPage) -> Name:
        """
        Parse a track name from a page that represents a Single release, and does not contain a (somewhat redundant)
        track list.
        """
        raise NotImplementedError

    @abstractmethod
    def process_album_editions(self, entry: DiscographyEntry, entry_page: WikiPage) -> EditionIterator:
        raise NotImplementedError

    @abstractmethod
    def process_edition_parts(self, edition: DiscographyEntryEdition) -> Iterator[DiscographyEntryPart]:
        raise NotImplementedError

    # endregion

    # region Show / OST

    @abstractmethod
    def parse_soundtrack_links(self, page: WikiPage) -> Iterator[Link]:
        raise NotImplementedError

    @abstractmethod
    def parse_source_show(self, page: WikiPage) -> Optional[TVSeries]:
        raise NotImplementedError

    # endregion

    @classmethod
    def _check_type(cls, node, index, clz):
        try:
            return isinstance(node[index], clz)
        except (IndexError, KeyError, TypeError):
            return False
