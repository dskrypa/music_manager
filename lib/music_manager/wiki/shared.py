"""
:author: Doug Skrypa
"""

import logging
from enum import Enum

from ds_tools.compat import cached_property
from ds_tools.unicode import LangCat
from .utils import parse_date

__all__ = ['DiscoEntryType', 'DiscoEntry']
log = logging.getLogger(__name__)


class DiscoEntry:
    """
    A basic entry in an :class:`Artist<.artist.Artist>` or :class:`Discography<.discography.Discography>` page.

    May provide useful information when a full page does not exist for a given entry.
    """
    def __init__(self, source, node, *, title=None, type_=None, lang=None, date=None, year=None, link=None, song=None):
        """

        :param source: The page object where this entry was found
        :param node: The specific node on that page that represents this entry
        :param str title: The entry title
        :param type_: The type of album that this entry represents, i.e., mini album, single, etc.
        :param str|LangCat lang: The primary language for the entry
        :param str|datetime date: The date that the entry was released
        :param int year: The year that the entry was released, if the exact date is unavailable
        """
        self.source = source
        self.node = node
        self._title = title
        self._type = type_
        self.language = lang if lang is None or isinstance(lang, LangCat) else LangCat.for_name(lang)
        self.date = parse_date(date)
        self.year = year if year is not None else self.date.year if self.date else None
        self._link = link
        self.links = []
        self.song = song

    def __repr__(self):
        date = self.date.strftime('%Y-%m-%d') if self.date else self.year
        additional = ', '.join(filter(None, [self.type.real_name, self.language.full_name if self.language else None]))
        return f'<{type(self).__name__}[{self.title!r}, {date}] from {self.source}[{additional}]>'

    @property
    def link(self):
        if self._link:
            return self._link
        elif not self.links:
            return None

    @property
    def title(self):
        return self._title if self._title else (self.link.text or self.link.title) if self.link else None

    @title.setter
    def title(self, value):
        self._title = value

    @property
    def type(self):
        if self.title and (' OST ' in self.title or self.title.endswith(' OST')):
            return DiscoEntryType.Soundtrack            # Some sites put OSTs under 'Compilations / Other'
        elif isinstance(self._type, DiscoEntryType):
            return self._type
        return DiscoEntryType.for_name(self._type)

    @property
    def categories(self):
        return self.type.categories


class DiscoEntryType(Enum):
    UNKNOWN = 'UNKNOWN', ()
    MiniAlbum = 'Mini Album', ('mini album',)
    ExtendedPlay = 'EP', ('extended play',)
    SingleAlbum = 'Single Album', ('single album',)
    SpecialAlbum = 'Special Album', ('special album',)
    Compilation = 'Compilation', ('compilation', 'best album')
    Feature = 'Feature', ('feature',)
    Collaboration = 'Collaboration', ('collaboration',)
    Live = 'Live Album', ('live album',)
    MixTape = 'MixTape', ('mixtape',)
    CoverAlbum = 'Cover Album', ('cover album', 'remake album')
    Soundtrack = 'Soundtrack', ('soundtrack', 'ost')
    Single = 'Single', ('single', 'song', 'digital single', 'promotional single', 'special single', 'other release')
    Album = 'Album', ('studio album', 'repackage album', 'full-length album', 'album')

    def __repr__(self):
        return f'<{type(self).__name__}: {self.value[0]!r}>'

    @classmethod
    def for_name(cls, name):
        if name:
            if isinstance(name, str):
                name = [name]
            for _name in name:
                _name = _name.lower().strip().replace('-', ' ').replace('_', ' ')
                for album_type in cls:
                    if any(cat in _name for cat in album_type.categories):
                        return album_type
            log.debug(f'No DiscoEntryType exists for name={name!r}')
        return cls.UNKNOWN

    @cached_property
    def real_name(self):
        return self.value[0]

    @cached_property
    def categories(self):
        return self.value[1]
