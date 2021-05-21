"""
High level PySimpleGUI elements that represent Plex objects

:author: Doug Skrypa
"""

import logging
from datetime import datetime
from itertools import count
from pathlib import Path
from tempfile import gettempdir

from plexapi.audio import Track  #, Audio, Album, Artist
# from plexapi.playlist import Playlist
# from plexapi.video import Video, Movie, Show, Season, Episode
from PySimpleGUI import Column, Text
from requests import RequestException

from ...common.images import as_image, scale_image, ImageType
from ..elements import ExtendedImage, Rating

__all__ = ['TrackRow']
log = logging.getLogger(__name__)
ICONS_DIR = Path(__file__).resolve().parents[4].joinpath('icons')
TMP_DIR = Path(gettempdir()).joinpath('plex', 'images')


class TrackRow:
    __counter = count()

    def __init__(self, cover_size: tuple[int, int] = None):
        self.cover_size = cover_size or (40, 40)
        self._num = num = next(self.__counter)
        self.cover = ExtendedImage(size=self.cover_size, key=f'track:{num}:cover')
        self.year = Text(size=(4, 1), key=f'track:{num}:year')
        self.artist = Text(size=(20, 1), key=f'track:{num}:artist')
        self.album = Text(size=(20, 1), key=f'track:{num}:album')
        self.title = Text(size=(20, 1), key=f'track:{num}:title')
        self.duration = Text(size=(5, 1), key=f'track:{num}:duration')
        self.views = Text(size=(5, 1), key=f'track:{num}:views')
        self.rating = Rating(key=f'track:{num}:rating')
        row = [self.cover, self.year, self.artist, self.album, self.title, self.duration, self.views, self.rating]
        self.column = Column(
            [row],
            key=f'track:{num}:column',
            visible=False,
            justification='center',
            element_justification='center',
            expand_x=True,
        )

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
        self.year.update(track._data.attrib.get('parentYear'))
        self.artist.update(track.grandparentTitle)
        self.album.update(track.parentTitle)
        self.title.update(track.title)
        duration = int(track.duration / 1000)
        duration_dt = datetime.fromtimestamp(duration)
        self.duration.update(duration_dt.strftime('%M:%S' if duration < 3600 else '%H:%M:%S'))
        self.views.update(track.viewCount)
        self.rating.update(track.userRating)
        self.cover.image = self._get_images(track)
        self.column.update(visible=True)

    def _get_images(self, track: Track):
        full_size_path = TMP_DIR.joinpath(track.thumb[1:])
        thumb_path = full_size_path.with_name('{}__{}x{}'.format(full_size_path.name, *self.cover_size))
        if thumb_path.exists():
            return thumb_path, full_size_path
        elif full_size_path.exists():
            return self._convert_and_save_thumbnail(full_size_path, thumb_path), full_size_path

        server = track._server
        try:
            resp = server._session.get(server.url(track.thumb), headers=server._headers())
        except RequestException as e:
            log.debug(f'Error retrieving cover for {track}: {e}')
            return ICONS_DIR.joinpath('x.png')
        else:
            if not full_size_path.parent.exists():
                full_size_path.parent.mkdir(parents=True)
            log.debug(f'Saving cover image for {track} to {full_size_path.as_posix()}')
            image_bytes = resp.content
            with full_size_path.open('wb') as f:
                f.write(image_bytes)
            return self._convert_and_save_thumbnail(image_bytes, thumb_path), full_size_path

    def _convert_and_save_thumbnail(self, image: ImageType, thumb_path: Path):
        thumbnail = scale_image(as_image(image), *self.cover_size)
        if not thumb_path.parent.exists():
            thumb_path.parent.mkdir(parents=True)
        log.debug(f'Saving cover image thumbnail for to {thumb_path.as_posix()}')
        with thumb_path.open('wb') as f:
            thumbnail.save(f, 'png' if thumbnail.mode == 'RGBA' else 'jpeg')
        return thumbnail
