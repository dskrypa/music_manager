"""
Album / track formatting helper functions.

:author: Doug Skrypa
"""

import logging
from functools import cached_property
from io import BytesIO
from typing import TYPE_CHECKING, Optional, Any

from PySimpleGUI import Text, Input, Image, Multiline, HorizontalSeparator, Column, Element, VerticalSeparator, popup_ok

from ...constants import typed_tag_name_map
from ...files.album import AlbumDir
from ...files.track.track import SongFile
from ...manager.update import AlbumInfo, TrackInfo
from .utils import resize_text_column, label_and_val_key

if TYPE_CHECKING:
    from .base import GuiView

__all__ = ['TrackBlock', 'AlbumBlock']
log = logging.getLogger(__name__)


class AlbumBlock:
    def __init__(self, view: 'GuiView', album_dir: AlbumDir, cover_size: tuple[int, int] = (250, 250)):
        self.view = view
        self.album_dir = album_dir
        self.album_info = AlbumInfo.from_album_dir(album_dir)
        self.cover_size = cover_size

    @cached_property
    def track_blocks(self):
        blocks = {}
        for track in self.album_dir:
            path = track.path.as_posix()
            info = self.album_info.tracks[path]
            blocks[path] = TrackBlock(track, info, self.cover_size)
        return blocks

    def __iter__(self):
        yield from self.track_blocks.values()

    @cached_property
    def _cover_image_data(self) -> set[bytes]:
        return set(filter(None, (tb._cover_image_data for tb in self.track_blocks.values())))

    @property
    def cover_image(self) -> Image:
        key = 'album_cover'
        cover_images = self._cover_image_data
        if len(cover_images) == 1:
            return Image(data=next(iter(cover_images)), size=self.cover_size, key=key)
        elif cover_images:
            popup_ok(f'Warning: found {len(cover_images)} cover images for {self.album_dir}')
        return Image(size=self.cover_size, key=key)

    def get_album_data_rows(self, editable: bool = False):
        rows = []
        skip = {'tracks'}
        always_ro = {'mp4'}
        for key, value in self.album_info.to_dict().items():
            if key in skip:
                continue

            key_ele, val_key = label_and_val_key('album', key)
            disp_value = repr(value) if value is not None and not isinstance(value, str) else value
            val_ele = Input(disp_value, key=val_key, disabled=not editable or key in always_ro)
            rows.append([key_ele, val_ele])

        return resize_text_column(rows)

    # def get_album_diff_rows(self, ):


class TrackBlock:
    def __init__(self, track: SongFile, info: TrackInfo, cover_size: tuple[int, int] = (250, 250)):
        self.track = track
        self.cover_size = cover_size
        self.info = info

    @cached_property
    def _cover_image_data(self) -> Optional[bytes]:
        try:
            image = self.track.get_cover_image()
        except Exception:
            log.error(f'Unable to load cover image for {self.track}')
            return None
        else:
            image.thumbnail(self.cover_size)
            bio = BytesIO()
            image.save(bio, format='PNG')
            return bio.getvalue()

    @property
    def cover_image(self) -> Image:
        # If self._cover_image_data is None, it will be a blank frame
        return Image(data=self._cover_image_data, size=self.cover_size, key=f'img::{self.path_str}::cover')

    @cached_property
    def tag_values(self) -> dict[str, tuple[str, Any]]:
        tag_name_map = typed_tag_name_map.get(self.track.tag_type, {})
        tag_values = {}
        for tag, val in sorted(self.track.tags.items()):
            tag_name = tag_name_map.get(tag[:4], tag)
            if tag_name == 'Album Cover':
                continue

            tag_values[tag] = (tag_name, val)
        return tag_values

    @cached_property
    def path_str(self) -> str:
        return self.track.path.as_posix()

    def get_tag_rows(self, editable: bool = True) -> list[list[Element]]:
        rows = []
        for tag, (tag_name, val) in self.tag_values.items():
            key_ele = Text(tag_name, key=f'tag::{self.path_str}::{tag}')
            val_key = f'val::{self.path_str}::{tag}'
            if tag_name == 'Lyrics':
                val_ele = Multiline(val, size=(45, 4), key=val_key, disabled=not editable)
            else:
                val_ele = Input(val, key=val_key, disabled=not editable)

            rows.append([key_ele, val_ele])

        return resize_text_column(rows)

    def get_info_rows(self, editable: bool = True):
        rows = []
        for key, value in self.info.to_dict().items():
            key_ele, val_key = label_and_val_key(self.path_str, key)
            val_ele = Input(value, key=val_key, disabled=not editable)
            rows.append([key_ele, val_ele])

        return resize_text_column(rows)

    def get_basic_info_row(self):
        track = self.track
        return [
            Text('File:'),
            Input(track.path.name, size=(50, 1), disabled=True),
            VerticalSeparator(),
            Text('Length:'),
            Input(track.length_str, size=(6, 1), disabled=True),
            VerticalSeparator(),
            Text('Type:'),
            Input(track.tag_version, size=(10, 1), disabled=True),
        ]

    def as_info_rows(self, editable: bool = True):
        yield [HorizontalSeparator()]
        yield self.get_basic_info_row()
        yield [Column(self.get_info_rows(editable))]

    def as_all_tag_rows(self, editable: bool = True):
        yield [HorizontalSeparator()]
        yield self.get_basic_info_row()
        yield [Column([[self.cover_image]]), Column(self.get_tag_rows(editable))]
