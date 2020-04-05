"""
:author: Doug Skrypa
"""

import logging

from ds_tools.core import Paths
from ds_tools.output import uprint
from ..files import AlbumDir, iter_album_dirs
from ..wiki.artist import Artist
from .exceptions import NoArtistFoundException

__all__ = ['find_artist', 'show_matches']
log = logging.getLogger(__name__)


def show_matches(paths: Paths):
    for album_dir in iter_album_dirs(paths):
        try:
            artist = find_artist(album_dir)
        except NoArtistFoundException:
            log.error(f'No artist could be found for {album_dir}')
        else:
            uprint(f'- Album: {album_dir}')
            uprint(f'    - Artist: {artist} / {artist.name}')


def find_artist(album_dir: AlbumDir) -> Artist:
    if artist := album_dir.artist:
        if artist.english:
            return Artist.from_title(artist.english, search=True)

    if artists := album_dir.artists:
        for artist in artists:
            if artist.english:
                return Artist.from_title(artist.english, search=True)

    raise NoArtistFoundException(album_dir)
