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
from tk_gui.elements import Element, ListBox, CheckBox
from tk_gui.elements.frame import InteractiveFrame
from tk_gui.elements.rating import Rating
from tk_gui.elements.text import normalize_text_ele_widths, PathLink, Multiline, Text, Input
from tk_gui.popups import BasicPopup
from tk_gui.style import StyleState

from music.common.ratings import stars_from_256
from music.files.track.track import SongFile
from music.manager.update import TrackInfo
from .list_box import EditableListBox
from .menus import TextRightClickMenu, EditableTextRightClickMenu

if TYPE_CHECKING:
    from tkinter import Event
    from tk_gui.typing import Layout, Bool, BindCallback

__all__ = ['TrackInfoFrame', 'SongFileFrame']
log = logging.getLogger(__name__)


class TrackMixin:
    disabled: bool
    track: TrackInfo | SongFile

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__}[track={self.track!r}]>'

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

    def _build_rating(self, key: str, value, suffix: str = None):
        return Rating(value, key=self._val_key(key, suffix), show_value=True, pad=(0, 0), disabled=self.disabled)

    def _rating_row(self, key: str, value, suffix: str = None):
        return [self._key_text(key, suffix), self._build_rating(key, value, suffix)]


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
        self._tag_id_rows_map = defaultdict(list)
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
        tag_id_rows_map = self._tag_id_rows_map
        for tag_id, n, row in self._build_tag_rows():
            tag_id_rows_map[tag_id].append(row)
            yield row

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

    def get_tag_rows(self, tag_id: str) -> list[list[Element]]:
        try:
            return self._tag_id_rows_map[tag_id]
        except KeyError:
            return []

    def _build_tag_rows(self):
        nums = defaultdict(count)
        for trunc_id, tag_id, tag_name, disp_name, val in sorted(self.track.iter_tag_id_name_values()):
            if disp_name == 'Album Cover':
                continue

            # self.log.debug(f'Making tag row for {tag_id=} {tag_name=} {disp_name=} {val=}')
            n = next(nums[tag_id])
            uniq_id = f'{tag_id}--{n}' if n else tag_id
            yield tag_id, n, self._build_tag_row(tag_id, uniq_id, disp_name, val)

    def _build_tag_row(
        self, tag_id: str, uniq_id: str, disp_name: str, val: Any
    ) -> tuple[Text, Text | Multiline | Rating | ListBox]:
        key_ele = Text(disp_name, tooltip=uniq_id)
        if disp_name == 'Lyrics':
            binds = {'<Control-Button-1>': self._lyrics_popup_cb()}
            val_ele = Multiline(val, size=(45, 4), read_only=True, tooltip='Pop out with ctrl + click', binds=binds)
        elif disp_name == 'Rating':
            try:
                rating = stars_from_256(int(val), 10)
            except (ValueError, TypeError):
                val_ele = Text(val, size=(30, 1), use_input_style=True)
            else:
                val_ele = self._build_rating(disp_name, rating)
        elif disp_name == 'Genre':
            kwargs = {'size': (30, len(val)), 'pad': (5, 0), 'border': 2}
            val_ele = ListBox(val, default=val, disabled=self.disabled, scroll_y=False, **kwargs)
        else:
            val_ele = Text(val, size=(30, 1), use_input_style=True)

        return (key_ele, val_ele)

    def _lyrics_popup_cb(self):
        def lyrics_popup(event: Event):
            track = self.track
            lyrics = track.get_tag_value_or_values('lyrics')
            title = f'Lyrics: {track.tag_artist} - {track.tag_album} - {track.tag_title}'
            # font = ('sans-serif', 14)
            BasicPopup(lyrics, title=title, multiline=True).run()

        return lyrics_popup


class SelectableSongFileFrame(SongFileFrame):
    # TODO: Add button/prompt to add a new tag?

    def __init__(self, *args, multi_select_cb: BindCallback = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._multi_select_cb = multi_select_cb
        self.to_delete = set()

    def _build_tag_row(
        self, tag_id: str, uniq_id: str, disp_name: str, val: Any
    ) -> tuple[Text, CheckBox, Text | Multiline | Rating | ListBox]:
        data = {'track_frame': self, 'tag_id': tag_id}
        key_ele, val_ele = super()._build_tag_row(tag_id, uniq_id, disp_name, val)
        sel_box = CheckBox('', disabled=self.disabled, data=data)

        def box_toggled_callback(*args):
            layer, state = val_ele.base_style_layer_and_state
            if sel_box.value:  # The tag is marked for deletion
                state = StyleState.INVALID  # Re-using this state since it typically makes the background red
                self.to_delete.add(tag_id)
            else:
                self.to_delete.discard(tag_id)

            fg, bg = layer.fg[state], layer.bg[state]
            kwargs = {'fg': fg, 'bg': bg}
            if isinstance(val_ele, Text):
                kwargs['readonlybackground'] = bg
            elif isinstance(val_ele, ListBox):
                kwargs['selectforeground'] = val_ele.style.selected.fg[state]
                kwargs['selectbackground'] = val_ele.style.selected.bg[state]

            val_ele.update_style(**kwargs)

        sel_box.change_cb = box_toggled_callback
        binds = {'<Button-1>': sel_box.toggle_as_callback()}
        if multi_select_cb := self._multi_select_cb:
            binds['<Shift-Button-1>'] = multi_select_cb
            sel_box.bind('<Shift-Button-1>', multi_select_cb)

        for ele in (key_ele, val_ele):
            ele.data = data
            for bind_key, cb in binds.items():
                ele.bind(bind_key, cb)

        return (key_ele, sel_box, val_ele)
