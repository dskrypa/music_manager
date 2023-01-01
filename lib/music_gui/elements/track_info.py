"""

"""

from __future__ import annotations

import logging
from abc import abstractmethod
from collections import defaultdict
from itertools import count
from pathlib import Path
from typing import TYPE_CHECKING, Iterator, Any, Collection

from ds_tools.caching.decorators import cached_property
from tk_gui.elements import Element, ListBox
from tk_gui.elements.frame import InteractiveFrame
from tk_gui.elements.rating import Rating
from tk_gui.elements.text import normalize_text_ele_widths, PathLink, Multiline, Text, Input
from tk_gui.popups import BasicPopup

from music.common.ratings import stars_from_256
from music.files.track.track import SongFile
from music.manager.update import TrackInfo
from .list_box import EditableListBox
from .menus import TextRightClickMenu, EditableTextRightClickMenu

if TYPE_CHECKING:
    from tkinter import Event
    from tk_gui.typing import Layout

__all__ = ['TrackInfoFrame', 'SongFileFrame']
log = logging.getLogger(__name__)


class TrackMixin:
    disabled: bool

    def get_custom_layout(self) -> Layout:
        return normalize_text_ele_widths([row for row in self.build_rows()])  # noqa

    def build_rows(self) -> Iterator[list[Element]]:
        raise NotImplementedError

    @property
    @abstractmethod
    def path_str(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def file_name(self) -> str:
        raise NotImplementedError

    def key_for(self, type: str, field: str, suffix: str = None) -> str:  # noqa
        if suffix:
            return f'{type}::{self.path_str}::{field}::{suffix}'
        else:
            return f'{type}::{self.path_str}::{field}'

    def _val_key(self, key: str, suffix: str = None) -> str:
        return self.key_for('val', key, suffix)

    def _key_text(self, key: str, suffix: str = None) -> Text:
        return Text(key.replace('_', ' ').title(), key=self.key_for('tag', key, suffix))

    def _rating_row(self, key: str, value, suffix: str = None):
        row = [
            self._key_text(key, suffix),
            Rating(value, key=self._val_key(key, suffix), show_value=True, pad=(0, 0), disabled=self.disabled),
        ]
        return row


class TrackInfoFrame(TrackMixin, InteractiveFrame):
    track_info: TrackInfo

    def __init__(self, track: TrackInfo | SongFile, **kwargs):
        if not isinstance(track, TrackInfo):
            track = TrackInfo.from_file(track)
        self.track_info = track
        super().__init__(**kwargs)

    @cached_property
    def path_str(self) -> str:
        return self.track_info.path.as_posix()

    @cached_property
    def file_name(self) -> str:
        return self.track_info.path.name

    def build_info_rows(self, keys: Collection[str] = None) -> Iterator[list[Element]]:
        fields = ['artist', 'title', 'name', 'genre', 'disk', 'num']
        if keys:
            fields = [f for f in fields if f not in keys]

        menu = TextRightClickMenu() if self.disabled else EditableTextRightClickMenu()
        data = self.track_info.to_dict()
        text_keys = {'title', 'artist', 'name'}
        for key in fields:
            kwargs = {'key': self._val_key(key), 'disabled': self.disabled}
            if key in text_keys:
                kwargs['right_click_menu'] = menu

            if key == 'genre':
                add_prompt = f'Enter a new {key} value to add to {self.track_info.title!r}'
                val_ele = EditableListBox(data[key], add_title=f'Add {key}', add_prompt=add_prompt, **kwargs)
            else:
                val_ele = Input(data[key], size=(30, 1), **kwargs)

            yield [self._key_text(key), val_ele]

        if not keys or 'rating' in keys:
            yield self._rating_row('rating', data['rating'])

    def build_rows(self) -> Iterator[list[Element]]:
        yield from self.build_info_rows()


class SongFileFrame(TrackMixin, InteractiveFrame):
    track: SongFile

    def __init__(self, track: TrackInfo | SongFile | str | Path, **kwargs):
        if isinstance(track, TrackInfo):
            track = track.path
        if isinstance(track, (str, Path)):
            track = SongFile(track)
        self.track = track
        super().__init__(**kwargs)

    @cached_property
    def path_str(self) -> str:
        return self.track.path.as_posix()

    @cached_property
    def file_name(self) -> str:
        return self.track.path.name

    def build_rows(self) -> Iterator[list[Element]]:
        yield self.get_basic_info_row()
        yield self.get_metadata_row()
        yield from self.build_tag_rows()

    def get_basic_info_row(self):
        track = self.track
        tag_version = f'{track.tag_version} (lossless)' if track.lossless else track.tag_version
        link = PathLink(self.track.path, use_link_style=False, path_in_tooltip=True)
        return [
            Text('File:'), Text(self.file_name, size=(50, 1), link=link, use_input_style=True),
            Text('Length:'), Text(track.length_str, size=(6, 1), use_input_style=True),
            Text('Type:'), Text(tag_version, size=(20, 1), use_input_style=True),
        ]

    def get_metadata_row(self):
        info = self.track.info
        row = [
            Text('Bitrate:'), Text(info['bitrate_str'], size=(14, 1), use_input_style=True),
            Text('Sample Rate:'), Text(info['sample_rate_str'], size=(10, 1), use_input_style=True),
            Text('Bit Depth:'), Text(info['bits_per_sample'], size=(10, 1), use_input_style=True),
        ]
        for key in ('encoder', 'codec'):
            if value := info.get(key):
                row.append(Text(f'{key.title()}:'))
                row.append(Text(value, size=(15, 1)))
        return row

    def build_tag_rows(self):
        nums = defaultdict(count)
        for trunc_id, tag_id, tag_name, disp_name, val in sorted(self.track.iter_tag_id_name_values()):
            if disp_name == 'Album Cover':
                continue

            # self.log.debug(f'Making tag row for {tag_id=} {tag_name=} {disp_name=} {val=}')
            if n := next(nums[tag_id]):
                tag_id = f'{tag_id}--{n}'

            yield self._build_tag_row(tag_id, disp_name, val)

    def _build_tag_row(self, tag_id: str, disp_name: str, val: Any):
        key_ele = Text(disp_name, key=self.key_for('tag', tag_id), tooltip=tag_id)
        val_key = self.key_for('val', tag_id)
        if disp_name == 'Lyrics':
            binds = {'<Control-Button-1>': self._lyrics_popup_cb()}
            val_ele = Multiline(
                val, size=(45, 4), key=val_key, disabled=True, tooltip='Pop out with ctrl + click', binds=binds
            )
            return [key_ele, val_ele]
        elif disp_name == 'Rating':
            try:
                rating = stars_from_256(int(val), 10)
            except (ValueError, TypeError):
                return [key_ele, Text(val, key=val_key, size=(30, 1), use_input_style=True)]
            else:
                return self._rating_row(disp_name, rating)
        elif disp_name == 'Genre':
            kwargs = {
                'size': (30, len(val)),
                'pad': (5, 0),
                'border': 2,
            }
            return [key_ele, ListBox(val, default=val, disabled=self.disabled, scroll_y=False, key=val_key, **kwargs)]
        else:
            return [key_ele, Text(val, key=val_key, size=(30, 1), use_input_style=True)]

    def _lyrics_popup_cb(self):
        def lyrics_popup(event: Event):
            track = self.track
            lyrics = track.get_tag_value_or_values('lyrics')
            title = f'Lyrics: {track.tag_artist} - {track.tag_album} - {track.tag_title}'
            # font = ('sans-serif', 14)
            BasicPopup(lyrics, title=title, multiline=True).run()

        return lyrics_popup
