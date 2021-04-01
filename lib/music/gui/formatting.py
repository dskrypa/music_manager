"""
Formatting helper functions.

:author: Doug Skrypa
"""

import logging
from functools import cached_property
from io import BytesIO
from itertools import chain
from typing import TYPE_CHECKING, Optional

from PySimpleGUI import Text, Input, Image, Multiline, HorizontalSeparator, Column, Element, VerticalSeparator, Button
from PySimpleGUI import popup_ok

from ..constants import typed_tag_name_map
from ..files.album import AlbumDir
from ..files.track.track import SongFile
from ..manager.update import AlbumInfo, TrackInfo
from .constants import LoadingSpinner
from .progress import Spinner

if TYPE_CHECKING:
    from .base import GuiBase

__all__ = ['TrackBlock', 'AlbumBlock']
log = logging.getLogger(__name__)


class VScrollColumn(Column):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, scrollable=True, vertical_scroll_only=True, **kwargs)


class AlbumBlock:
    def __init__(self, gui: 'GuiBase', album_dir: AlbumDir, cover_size: tuple[int, int] = (250, 250)):
        self.gui = gui
        self.album_dir = album_dir
        self.album_info = AlbumInfo.from_album_dir(album_dir)
        self.cover_size = cover_size
        self.editing = False

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
            disp_value = repr(value) if value is not None and not isinstance(value, str) else value
            value = Input(disp_value, key=val_key, disabled=not editable or key in always_ro)
            rows.append([Text(key.replace('_', ' ').title(), key=tag_key), value])

        for row in rows:
            row[0].Size = (longest, 1)

        return rows

    def as_tag_rows(self):
        with Spinner(LoadingSpinner.blue_dots) as spinner:
            yield [Text('Album Path:'), Input(self.album_dir.path.as_posix(), disabled=True, size=(150, 1))]
            yield [HorizontalSeparator()]
            track_rows = list(chain.from_iterable(b.as_rows(False) for b in spinner(self.track_blocks.values())))
            win_w, win_h = self.gui.window.size
            yield [VScrollColumn(track_rows, key='col::track_data', size=(win_w - 20, win_h - 20))]

    def as_rows(self, editable: bool = True):
        with Spinner(LoadingSpinner.blue_dots) as spinner:
            yield [Text('Album Path:'), Input(self.album_dir.path.as_posix(), disabled=True, size=(150, 1))]
            yield [HorizontalSeparator()]

            spinner.update()
            btn_kw = {'size': (18, 1)}
            view_buttons = [
                Button('Edit', key='album::edit', **btn_kw), Button('View All Tags', key='album::all_tags', **btn_kw)
            ]
            edit_buttons = [
                Button('Review & Save Changes', key='album::save', **btn_kw),
                Button('Cancel', key='album::cancel', **btn_kw),
            ]
            album_container = Column(
                [
                    [
                        Column([[self.cover_image]], key='col::album_cover'),
                        Column(self.get_album_data_rows(editable), key='col::album_data'),
                    ],
                    [HorizontalSeparator()],
                    [
                        Column([view_buttons], key='col::view_buttons', visible=not editable),
                        Column([edit_buttons], key='col::edit_buttons', visible=editable),
                    ],
                ],
                vertical_alignment='top',
                element_justification='center',
                key='col::album_container',
            )

            track_rows = []
            for block in spinner(self.track_blocks.values()):
                track_rows.extend(block.as_info_rows(editable))

            track_data = VScrollColumn(track_rows, key='col::track_data', size=(685, 690))
            yield [Column([[album_container, track_data]], key='col::all_data')]

    def toggle_editing(self):
        self.editing = not self.editing
        always_ro = {'val::album::mp4'}
        for key, ele in self.gui.window.AllKeysDict.items():
            if isinstance(key, str) and key.startswith('val::') and key not in always_ro:
                ele.update(disabled=not self.editing)

        self.gui.window['col::view_buttons'].update(visible=not self.editing)
        # self.gui.window['edit_album'].update(visible=not self.editing)
        # self.gui.window['view_tags'].update(visible=not self.editing)
        self.gui.window['col::edit_buttons'].update(visible=self.editing)
        # self.gui.window['album_changes::save'].update(visible=self.editing)
        # self.gui.window['album_changes::cancel'].update(visible=self.editing)


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
