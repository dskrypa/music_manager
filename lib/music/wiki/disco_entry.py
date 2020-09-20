"""
:author: Doug Skrypa
"""

import logging
from functools import cached_property
from typing import Optional, Union, Mapping, Iterable, List

from ds_tools.unicode import LangCat
from wiki_nodes import WikiPage, Link
from wiki_nodes.nodes import N
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
    def __init__(
            self, source: WikiPage, node: N, *, title: Union[str, Name, None] = None,
            lang: Union[str, LangCat, None] = None, type_: Union[DiscoEntryType, str, Iterable[str], None] = None,
            date: DateObj = None, year: Optional[int] = None, link: Optional[Link] = None, song: Optional[str] = None,
            track_data: Optional[N] = None, from_albums: Optional[Mapping[str, Optional[Link]]] = None
    ):
        """
        A basic discography entry from an artist or artist discography page.

        :param WikiPage source: The :class:`WikiPage` object where this entry was found
        :param Node node: The specific :class:`Node` on that page that represents this entry
        :param str title: The entry title
        :param str|LangCat lang: The primary language for the entry
        :param type_: The type of album that this entry represents, i.e., mini album, single, etc.
        :param str|datetime date: The date that the entry was released
        :param int year: The year that the entry was released, if the exact date is unavailable
        :param link: The link to the full discography entry for this album, if known
        :param str song: A single song that the artist contributed to on in this album
        :param track_data: Data about tracks in the album that this entry represents
        :param dict from_albums: A mapping of {str(name): :class:`Link` or None} for the albums that this
          single / OST track / etc was in, if any.
        """
        self.source = source                                                        # type: WikiPage
        self.node = node                                                            # type: Optional[N]
        self._title = title                                                         # type: Union[str, Name, None]
        self._type = type_
        self.language = LangCat.for_name(lang) if isinstance(lang, str) else lang   # type: Optional[LangCat]
        self.date = parse_date(date)                                                # type: DateResult
        self.year = year if year else self.date.year if self.date else None         # type: Optional[int]
        self._link = link                                                           # type: Optional[Link]
        self.links = []                                                             # type: List[Link]
        self.song = song                                                            # type: Optional[str]
        self.track_data = track_data                                                # type: Optional[N]
        self.from_albums = from_albums                                  # type: Optional[Mapping[str, Optional[Link]]]

    def __repr__(self):
        date = self.date.strftime('%Y-%m-%d') if self.date else self.year
        tracks = f'tracks={len(self.track_data)}' if self.track_data else None
        lang = self.language.full_name if self.language else None
        from_album = f'from {self.from_albums!r}' if self.from_albums else None
        additional = ', '.join(filter(None, [self.type.real_name, lang, tracks, from_album]))
        return f'<{type(self).__name__}[{self.name}, {date}] from {self.source}[{additional}]>'

    @property
    def link(self):
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
    def title(self) -> Optional[str]:
        if title := self._title:
            return str(title)
        return self.link.show if self.link else None

    @title.setter
    def title(self, value):
        self._title = value

    @property
    def type(self):
        title = self.title
        if title and (' OST ' in title or title.endswith(' OST')):
            return DiscoEntryType.Soundtrack            # Some sites put OSTs under 'Compilations / Other'
        elif self.from_albums and any(' OST ' in a or a.endswith(' OST') for a in self.from_albums):
            return DiscoEntryType.Soundtrack
        elif isinstance(self._type, DiscoEntryType):
            return self._type
        return DiscoEntryType.for_name(self._type)

    @property
    def categories(self):
        return self.type.categories
