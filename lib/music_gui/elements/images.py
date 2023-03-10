"""
Helper utilities for working with album cover images
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional

from tk_gui.elements import Image, Frame
from tk_gui.images.icons import placeholder_icon_cache
from tk_gui.popups import popup_ok

from music.files import SongFile, TagNotFound
from music.manager.update import AlbumInfo

if TYPE_CHECKING:
    from tk_gui.typing import XY, ImageType
    from music.files.track.track import SongFile

__all__ = ['AlbumCoverImageBuilder', 'TrackCoverImageBuilder']
log = logging.getLogger(__name__)

_multiple_covers_warned = set()


class CoverImageBuilder(ABC):
    __slots__ = ('cover_size',)
    cover_size: XY

    def __init__(self, cover_size: XY = (250, 250)):
        self.cover_size = cover_size

    @property
    @abstractmethod
    def popup_title(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def _get_raw_cover_image(self) -> Optional[bytes]:
        raise NotImplementedError

    def make_thumbnail(self, **kwargs) -> Image:
        image = placeholder_icon_cache.image_or_placeholder(self._get_raw_cover_image(), self.cover_size)
        return Image(
            image=image, size=self.cover_size, popup=True, popup_title=self.popup_title, use_cache=True, **kwargs
        )

    def make_thumbnail_frame(self, **kwargs) -> Frame:
        width, height = self.cover_size
        return Frame([[self.make_thumbnail(**kwargs)]], size=(width + 10, height + 10), pack_propagate=False)

    def make_diff_thumbnails(self, new_image: ImageType) -> tuple[Image, Image]:
        old_image_ele = self.make_thumbnail()
        new_image_ele = Image(
            image=new_image, size=self.cover_size, popup=True, popup_title='New Album Cover', use_cache=True
        )
        return old_image_ele, new_image_ele


class AlbumCoverImageBuilder(CoverImageBuilder):
    __slots__ = ('album_info',)
    album_info: AlbumInfo

    def __init__(self, album_info: AlbumInfo, cover_size: XY = (250, 250)):
        super().__init__(cover_size)
        self.album_info = album_info

    @property
    def popup_title(self) -> str:
        return f'Album Cover: {self.album_info.name}'

    def _process_tracks(self) -> tuple[set[bytes], int]:
        images = set()
        missing = 0
        for track in self.album_info.tracks.values():
            try:
                if image := get_raw_cover_image(SongFile(track.path), True):
                    images.add(image)
            except TagNotFound:
                missing += 1

        return images, missing

    def _get_raw_cover_images(self) -> set[bytes]:
        images, missing = self._process_tracks()
        n_img = len(images)
        messages = []
        # if missing:
        #     messages.append(f'cover images were missing for {missing} tracks')
        if not n_img and not missing:
            messages.append('no cover images were found')
        elif n_img > 1:
            messages.append(f'{n_img} cover images were found')

        if messages and self.album_info.path not in _multiple_covers_warned:
            _multiple_covers_warned.add(self.album_info.path)
            popup_ok(f'Warning: {" and ".join(messages)} for {self.album_info}', keep_on_top=True)

        return images

    def _get_raw_cover_image(self) -> Optional[bytes]:
        if (images := self._get_raw_cover_images()) and len(images) == 1:
            return next(iter(images))
        return None


class TrackCoverImageBuilder(CoverImageBuilder):
    __slots__ = ('song_file',)
    song_file: SongFile

    def __init__(self, song_file: SongFile, cover_size: XY = (250, 250)):
        super().__init__(cover_size)
        self.song_file = song_file

    @property
    def popup_title(self) -> str:
        return f'Track Album Cover: {self.song_file.path.name}'

    def _get_raw_cover_image(self) -> Optional[bytes]:
        return get_raw_cover_image(self.song_file)


def get_raw_cover_image(track: SongFile, propagate_not_found: bool = False) -> Optional[bytes]:
    try:
        return track.get_cover_data()[0]
    except TagNotFound as e:
        log.warning(e)
        if propagate_not_found:
            raise
        return None
    except Exception:  # noqa
        log.error(f'Unable to load cover image for {track}', exc_info=True)
        return None
