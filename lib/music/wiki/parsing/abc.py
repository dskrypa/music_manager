"""
:author: Doug Skrypa
"""

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Generator

from wiki_nodes.http import MediaWikiClient
from wiki_nodes.nodes import Node
from wiki_nodes.page import WikiPage
from ...text.name import Name

if TYPE_CHECKING:
    from ..album import DiscographyEntry, DiscographyEntryEdition
    from ..discography import DiscographyEntryFinder

__all__ = ['WikiParser']
log = logging.getLogger(__name__)

EditionGenerator = Generator['DiscographyEntryEdition', None, None]


class WikiParser(ABC):
    _site_parsers = {}
    client = None

    # noinspection PyMethodOverriding
    def __init_subclass__(cls, site: str):
        WikiParser._site_parsers[site] = cls
        cls.client = MediaWikiClient(site)

    @classmethod
    def for_site(cls, site: str) -> 'WikiParser':
        return cls._site_parsers[site]

    @classmethod
    @abstractmethod
    def parse_artist_name(cls, artist_page: WikiPage) -> Generator[Name, None, None]:
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def parse_album_name(cls, node: Node) -> Name:
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def parse_track_name(cls, node: Node) -> Name:
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def process_disco_sections(cls, artist_page: WikiPage, finder: 'DiscographyEntryFinder') -> None:
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def process_album_editions(cls, entry: 'DiscographyEntry', entry_page: WikiPage) -> EditionGenerator:
        raise NotImplementedError

    @classmethod
    def _check_type(cls, node, index, clz):
        try:
            return isinstance(node[index], clz)
        except (IndexError, KeyError, TypeError):
            return False
