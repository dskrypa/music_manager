"""
:author: Doug Skrypa
"""

import logging
from enum import Enum

from ds_tools.unicode import LangCat
from .utils import parse_date

__all__ = ['AlbumType', 'DiscoEntry']
log = logging.getLogger(__name__)


class DiscoEntry:
    """
    A basic entry in an :class:`Artist<.artist.Artist>` or :class:`Discography<.discography.Discography>` page.

    May provide useful information when a full page does not exist for a given entry.
    """
    def __init__(self, source, node, *, title=None, type_=None, lang=None, date=None, year=None):
        """

        :param source: The page object where this entry was found
        :param node: The specific node on that page that represents this entry
        :param str title: The entry title
        :param str|AlbumType type_: The type of album that this entry represents, i.e., mini album, single, etc.
        :param str|LangCat lang: The primary language for the entry
        :param str|datetime date: The date that the entry was released
        :param int year: The year that the entry was released, if the exact date is unavailable
        """
        self.source = source
        self.node = node
        self.title = title
        self.type = type_ if type_ is None or isinstance(type_, AlbumType) else AlbumType.for_name(type_)
        self.language = lang if lang is None or isinstance(lang, LangCat) else LangCat.for_name(lang)
        self.date = parse_date(date)
        self.year = year if year is not None else self.date.year if self.date else None
        self.link = None

    def __repr__(self):
        title = self.title if self.title else (self.link.text or self.link.title) if self.link else None
        return f'<{type(self).__name__}[{title!r}, {self.date or self.year}] from {self.source}>'


class AlbumType(Enum):
    UNKNOWN = 'UNKNOWN', ()
    Album = 'Album', ('studio album', 'repackage album', 'full-length album')
    MiniAlbum = 'Mini Album', ('mini album',)
    ExtendedPlay = 'EP', ('ep', 'extended play')
    Soundtrack = 'Soundtrack', ('soundtrack', 'ost')
    Single = 'Single', ('single', 'song', 'digital single', 'promotional single', 'special single', 'other release')
    SingleAlbum = 'Single Album', ('single album',)
    SpecialAlbum = 'Special Album', ('special album',)
    Compilation = 'Compilation', ('compilation', 'best album')
    Collaboration = 'Collaboration', ('collaboration', 'collaboration single', 'collaborations and feature')
    Live = 'Live Album', ('live album',)
    MixTape = 'MixTape', ('mixtape',)
    CoverAlbum = 'Cover Album', ('cover album', 'remake album')

    def __repr__(self):
        return f'<{type(self).__name__}: {self.value[0]!r}>'

    @classmethod
    def for_name(cls, name):
        name = name.lower().strip().replace('-', ' ').replace('_', ' ')
        name = name[:-1] if name.endswith('s') else name
        for album_type in cls:
            if name in album_type.value[1]:
                return album_type
        return cls.UNKNOWN
