"""
High level PySimpleGUI elements that represent Plex objects

:author: Doug Skrypa
"""

import logging
from datetime import datetime
from itertools import count
from pathlib import Path
from typing import Iterable, Hashable

from plexapi.audio import Audio, Album, Artist, Track
from plexapi.playlist import Playlist
from plexapi.video import Video, Movie, Show, Season, Episode
from PySimpleGUI import Column, Text
from requests import RequestException

from ..elements import ExtendedImage, Rating

__all__ = ['TrackRow']
log = logging.getLogger(__name__)
ICONS_DIR = Path(__file__).resolve().parents[4].joinpath('icons')


class TrackRow:
    __counter = count()

    def __init__(self):
        self._num = num = next(self.__counter)
        self.cover = ExtendedImage(size=(40, 40), key=f'track:{num}:cover')  # TODO: Make clickable?
        self.year = Text(size=(4, 1), key=f'track:{num}:year')
        self.artist = Text(size=(20, 1), key=f'track:{num}:artist')
        self.album = Text(size=(20, 1), key=f'track:{num}:album')
        self.title = Text(size=(20, 1), key=f'track:{num}:title')
        self.duration = Text(size=(5, 1), key=f'track:{num}:duration')
        self.views = Text(size=(5, 1), key=f'track:{num}:views')
        self.rating = Rating(key=f'track:{num}:rating')
        row = [self.cover, self.year, self.artist, self.album, self.title, self.duration, self.views, self.rating]
        self.column = Column([row], key=f'track:{num}:column', visible=False)

    def hide(self):
        self.column.update(visible=False)

    def clear(self, hide: bool = True):
        if hide:
            self.hide()
        self.year.update('')
        self.artist.update('')
        self.album.update('')
        self.title.update('')
        self.duration.update('')
        self.views.update('')
        self.cover.image = None
        self.rating.update(0)

    def update(self, track: Track):
        self.year.update(track.year)
        self.artist.update(track.grandparentTitle)
        self.album.update(track.parentTitle)
        self.title.update(track.title)
        duration = int(track.duration / 1000)
        duration_dt = datetime.fromtimestamp(duration)
        self.duration.update(duration_dt.strftime('%M:%S' if duration < 3600 else '%H:%M:%S'))
        self.views.update(track.viewCount)
        self.rating.update(track.userRating)
        server = track._server
        try:
            # TODO: Cache the resized thumbnails
            resp = server._session.get(server.url(track.thumb), headers=server._headers())
        except RequestException as e:
            log.debug(f'Error retrieving cover for {track}: {e}')
            self.cover.image = ICONS_DIR.joinpath('x.png')
        else:
            self.cover.image = resp.content
        self.column.update(visible=True)
