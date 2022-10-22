"""
:author: Doug Skrypa
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Union

if TYPE_CHECKING:
    from ..wiki.album import DEPart, DEEdition, DiscoObj

__all__ = ['WikiMatchException', 'NoArtistMatchFoundException', 'MatchException', 'NoArtistFoundError']


class WikiMatchException(Exception):
    """Base exception for errors during wiki match attempts"""


class NoArtistMatchFoundException(WikiMatchException):
    """Exception to be raised when no artist can be found for a given album"""


class MatchException(WikiMatchException):
    """Exception to be raised when a match cannot be found"""
    def __init__(self, lvl, msg):
        super().__init__(msg)
        self.lvl = lvl


class NoArtistFoundError(WikiMatchException):
    """No artist page/entity could be found for a given album"""

    def __init__(self, album: DiscoObj, artist_source: Union[str, DEPart, DEEdition]):
        self.album = album
        self.artist_source = artist_source

    def __str__(self) -> str:
        return f'No artist could be found for album={self.album} from source={self.artist_source}'
