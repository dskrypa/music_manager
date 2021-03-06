"""
Formatting helper functions.

:author: Doug Skrypa
"""

import logging
from functools import cached_property
from io import BytesIO
from typing import Optional

from PySimpleGUI import Text, Input, Image, Multiline, HorizontalSeparator, Column, Element, VerticalSeparator, Button
from PySimpleGUI import popup_ok, popup_animated

from ..constants import typed_tag_name_map
from ..files.album import AlbumDir
from ..files.track.track import SongFile
from ..manager.update import AlbumInfo, TrackInfo
from .constants import LoadingSpinner

__all__ = ['TrackBlock', 'AlbumBlock']
log = logging.getLogger(__name__)


class AlbumBlock:
    def __init__(self, album_dir: AlbumDir, cover_size: tuple[int, int] = (250, 250)):
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
        longest = 0
        skip = {'tracks'}
        always_ro = {'mp4'}
        for key, value in self.album_info.to_dict().items():
            if key in skip:
                continue

            longest = max(longest, len(key))
            tag_key = f'key::album::{key}'
            val_key = f'val::album::{key}'
            value = Input(value, key=val_key, disabled=not editable or key in always_ro)
            rows.append([Text(key.replace('_', ' ').title(), key=tag_key), value])

        for row in rows:
            row[0].Size = (longest, 1)

        return rows

    def as_rows(self, editable: bool = True):
        popup_animated(LoadingSpinner.blue_dots)
        yield [Text('Album Path:'), Input(self.album_dir.path.as_posix(), disabled=True, size=(150, 1))]
        yield [HorizontalSeparator()]

        popup_animated(LoadingSpinner.blue_dots)
        album_container = Column(
            [
                [
                    Column([[self.cover_image]], key='col::album_cover'),
                    Column(self.get_album_data_rows(editable), key='col::album_data'),
                ],
                [HorizontalSeparator()],
                [Button('Edit...', size=(16, 1), key='edit', visible=not editable)],
                [Button('Save Changes', size=(16, 1), key='save', visible=editable)],
            ],
            vertical_alignment='top',
            element_justification='center',
            key='col::album_container'
        )

        track_rows = []
        for block in self.track_blocks.values():
            popup_animated(LoadingSpinner.blue_dots)
            track_rows.extend(block.as_info_rows(editable))

        track_data = Column(track_rows, scrollable=True, vertical_scroll_only=True, key='col::track_data')

        yield [Column([[album_container, track_data]], key='col::all_data')]
        popup_animated(None)


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
        key = f'{self.track.path.as_posix()} -- cover'
        if data := self._cover_image_data:
            return Image(data=data, size=self.cover_size, key=key)
        return Image(size=self.cover_size, key=key)

    @cached_property
    def tag_values(self):
        tag_name_map = typed_tag_name_map.get(self.track.tag_type, {})
        tag_values = {}
        for tag, val in sorted(self.track.tags.items()):
            tag_name = tag_name_map.get(tag[:4], tag)
            if tag_name == 'Album Cover':
                continue

            tag_values[tag] = (tag_name, val)
        return tag_values

    def get_tag_rows(self, editable: bool = True) -> list[list[Element]]:
        rows = []
        longest = 0
        track_path = self.track.path.as_posix()
        for tag, (tag_name, val) in self.tag_values.items():
            longest = max(longest, len(tag_name))
            tag_key = f'{track_path} -- tag -- {tag}'
            val_key = f'{track_path} -- val -- {tag}'
            if tag_name == 'Lyrics':
                value = Multiline(val, size=(45, 4), key=val_key, disabled=not editable)
            else:
                value = Input(val, key=val_key, disabled=not editable)

            rows.append([Text(tag_name, key=tag_key), value])

        for row in rows:
            row[0].Size = (longest, 1)

        return rows

    def get_info_rows(self, editable: bool = True):
        rows = []
        longest = 0
        track_path = self.track.path.as_posix()
        for key, value in self.info.to_dict().items():
            longest = max(longest, len(key))
            tag_key = f'key::{track_path}::{key}'
            val_key = f'val::{track_path}::{key}'
            value = Input(value, key=val_key, disabled=not editable)
            rows.append([Text(key.replace('_', ' ').title(), key=tag_key), value])

        for row in rows:
            row[0].Size = (longest, 1)

        return rows

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

    def as_rows(self, editable: bool = True):
        yield [HorizontalSeparator()]
        yield self.get_basic_info_row()
        yield [Column([[self.cover_image]]), Column(self.get_tag_rows(editable))]
