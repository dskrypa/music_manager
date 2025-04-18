"""
:author: Doug Skrypa
"""

from __future__ import annotations

import logging
from typing import Mapping, Iterable

from ds_tools.caching.decorators import cached_property
from ds_tools.unicode import LangCat
from wiki_nodes.nodes import N, Link
from wiki_nodes.page import WikiPage

from ..common.disco_entry import DiscoEntryType
from ..text.name import Name
from ..text.time import parse_date, DateObj, DateResult

__all__ = ['DiscoEntry']
log = logging.getLogger(__name__)


class DiscoEntry:
    """
    A basic entry in an :class:`Artist<.artist.Artist>` or :class:`Discography<.discography.Discography>` page.

    May provide useful information when a full page does not exist for a given entry.
    """

    source: WikiPage
    node: N | None
    _title: str | Name | None
    language: LangCat | None
    date: DateResult
    year: int | None
    _link: Link | None
    links: list[Link]
    song: str | None
    track_data: N | None
    from_albums: Mapping[str, Link | None] | None

    def __init__(
        self,
        source: WikiPage,
        node: N,
        *,
        title: str | Name = None,
        lang: str | LangCat = None,
        type_: DiscoEntryType | str | Iterable[str] = None,
        date: DateObj = None,
        year: int = None,
        link: Link = None,
        song: str = None,
        track_data: N = None,
        from_albums: Mapping[str, Link | None] = None,
    ):
        """
        A basic discography entry from an artist or artist discography page.

        :param source: The :class:`WikiPage` object where this entry was found
        :param node: The specific :class:`Node` on that page that represents this entry
        :param title: The entry title
        :param lang: The primary language for the entry
        :param type_: The type of album that this entry represents, i.e., mini album, single, etc.
        :param date: The date that the entry was released
        :param year: The year that the entry was released, if the exact date is unavailable
        :param link: The link to the full discography entry for this album, if known
        :param song: A single song that the artist contributed to on in this album
        :param track_data: Data about tracks in the album that this entry represents
        :param from_albums: A mapping of {str(name): :class:`Link` or None} for the albums that this
          single / OST track / etc was in, if any.
        """
        self.source = source
        self.node = node
        self._title = title
        self._type = type_
        self.language = LangCat.for_name(lang) if isinstance(lang, str) else lang
        self.date = parse_date(date)
        self.year = year if year else self.date.year if self.date else None
        self._link = link
        self.links = []
        self.song = song
        self.track_data = track_data
        self.from_albums = from_albums

    def __repr__(self) -> str:
        date = self.date.strftime('%Y-%m-%d') if self.date else self.year
        tracks = f'tracks={len(self.track_data)}' if self.track_data else None
        lang = self.language.full_name if self.language else None
        from_album = f'from {self.from_albums!r}' if self.from_albums else None
        additional = ', '.join(filter(None, [self.type.real_name, lang, tracks, from_album]))
        return f'<{type(self).__name__}[{self.name}, {date}] from {self.source}[{additional}]>'

    @property
    def link(self) -> Link | None:
        if self._link:
            return self._link
        if links := self.links:
            return links[0]
        else:
            return None

    @cached_property
    def name(self) -> Name:
        if (title := self._title) and isinstance(title, Name):
            return title
        elif title := self.title:
            return Name.from_enclosed(title)
        return Name()

    @property
    def title(self) -> str | None:
        if title := self._title:
            return str(title)
        return self.link.show if self.link else None

    @title.setter
    def title(self, value: str):
        self._title = value

    @property
    def type(self) -> DiscoEntryType:
        title = self.title
        if title and (' OST ' in title or title.endswith(' OST')):
            return DiscoEntryType.Soundtrack            # Some sites put OSTs under 'Compilations / Other'
        elif self.from_albums and any(' OST ' in a or a.endswith(' OST') for a in self.from_albums):
            return DiscoEntryType.Soundtrack
        elif isinstance(self._type, DiscoEntryType):
            return self._type
        return DiscoEntryType.for_name(self._type)

    @property
    def categories(self) -> tuple[str, ...]:
        return self.type.categories
