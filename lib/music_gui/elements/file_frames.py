"""

"""

from __future__ import annotations

import logging
from collections import defaultdict
from itertools import count
from typing import TYPE_CHECKING, Any

from ds_tools.caching.decorators import cached_property
from tk_gui.elements import Element, ListBox, CheckBox, Image
from tk_gui.elements.frame import InteractiveFrame, Frame
from tk_gui.elements.rating import Rating
from tk_gui.elements.text import PathLink, Multiline, Text
from tk_gui.enums import StyleState
from tk_gui.popups import BasicPopup

from music.common.ratings import stars_from_256
from music.files.track.track import SongFile
from ..utils import TrackIdentifier, get_track_file
from .helpers import IText
from .images import TrackCoverImageBuilder

if TYPE_CHECKING:
    from tkinter import Event
    from tk_gui.typing import Layout, Bool, BindCallback, XY

__all__ = ['SongFileFrame', 'SelectableSongFileFrame']
log = logging.getLogger(__name__)

ValueEle = Text | Multiline | Rating | ListBox


class SongFileFrame(InteractiveFrame):
    track: SongFile
    show_cover: Bool = False

    def __init__(
        self,
        track: TrackIdentifier,
        show_cover: Bool = True,
        cover_size: XY = (250, 250),
        **kwargs,
    ):
        self.track = get_track_file(track)
        self.show_cover = show_cover
        self.cover_size = cover_size
        self._tag_id_rows_map = defaultdict(list)
        super().__init__(**kwargs)

    @cached_property
    def path_str(self) -> str:
        return self.track.path.as_posix()

    @cached_property
    def file_name(self) -> str:
        return self.track.path.name

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__}[track={self.track!r}]>'

    def get_tag_rows(self, tag_id: str) -> list[list[Element]]:
        try:
            return self._tag_id_rows_map[tag_id]
        except KeyError:
            return []

    # region Cover Image

    @property
    def cover_image_thumbnail(self) -> Image:
        return TrackCoverImageBuilder(self.track, self.cover_size).make_thumbnail()

    # endregion

    # region Build Rows

    def get_custom_layout(self) -> Layout:
        yield self._build_basic_info_row()
        yield self._build_metadata_row()
        if self.show_cover:
            yield [self.cover_image_thumbnail, Frame(list(self.build_tag_rows()))]
        else:
            yield from self.build_tag_rows()

    def _build_basic_info_row(self):
        track = self.track
        tag_version = f'{track.tag_version} (lossless)' if track.lossless else track.tag_version
        link = PathLink(self.track.path, use_link_style=False, path_in_tooltip=True)
        return [
            Text('File:', size=(8, 1)), IText(self.file_name, size=(50, 1), link=link),
            Text('Length:'), IText(track.length_str, size=(6, 1)),
            Text('Type:'), IText(tag_version, size=(20, 1)),
        ]

    def _build_metadata_row(self):
        info = self.track.info
        row = [
            Text('Bitrate:', size=(8, 1)), IText(info['bitrate_str'], size=(14, 1)),
            Text('Sample Rate:'), IText(info['sample_rate_str'], size=(10, 1)),
            Text('Bit Depth:'), IText(info['bits_per_sample'], size=(10, 1)),
        ]
        for key in ('encoder', 'codec'):
            if value := info.get(key):
                row += [Text(f'{key.title()}:'), IText(value, size=(15, 1))]
        return row

    def build_tag_rows(self):
        tag_id_rows_map = self._tag_id_rows_map
        for tag_id, n, row in self._build_tag_rows():
            tag_id_rows_map[tag_id].append(row)
            yield row

    @cached_property
    def _label_len(self) -> int:
        # Note: 8 is the length of the longest first static tag: `Bitrate:`
        lengths = (8, *(len(disp_name) for trunc_id, tag_id, tag_name, disp_name, val in self._tag_id_name_values))
        return max(lengths)

    @cached_property
    def _tag_id_name_values(self):
        return [
            (trunc_id, tag_id, tag_name, disp_name, val)
            for trunc_id, tag_id, tag_name, disp_name, val in sorted(self.track.iter_tag_id_name_values())
            if disp_name != 'Album Cover'
        ]

    def _build_tag_rows(self):
        nums = defaultdict(count)
        for trunc_id, tag_id, tag_name, disp_name, val in self._tag_id_name_values:
            # self.log.debug(f'Making tag row for {tag_id=} {tag_name=} {disp_name=} {val=}')
            n = next(nums[tag_id])
            uniq_id = f'{tag_id}--{n}' if n else tag_id
            yield tag_id, n, self._build_tag_row(tag_id, uniq_id, disp_name, val)

    def _build_tag_row(self, tag_id: str, uniq_id: str, disp_name: str, value: Any) -> tuple[Text, ValueEle]:
        # TODO: The key for wiki album/artist displays "User-defined URL" (only for MP3s)
        key_ele = Text(disp_name, tooltip=uniq_id, size=(self._label_len, 1))
        if disp_name == 'Lyrics':
            binds = {'<Control-Button-1>': self._lyrics_popup_cb()}
            val_ele = Multiline(value, size=(48, 4), read_only=True, tooltip='Pop out with ctrl + click', binds=binds)
        elif disp_name == 'Rating':
            try:
                rating = stars_from_256(int(value), 10)
            except (ValueError, TypeError):
                val_ele = IText(value, size=(50, 1))
            else:
                val_ele = Rating(rating, show_value=True, pad=(0, 0), disabled=self.disabled)
        elif disp_name == 'Genre':
            kwargs = {'size': (50, len(value)), 'pad': (5, 0), 'border': 2}
            val_ele = ListBox(value, default=value, disabled=self.disabled, scroll_y=False, **kwargs)
        else:
            if value is None:
                value = ''
            val_ele = IText(value, size=(50, 1))

        return (key_ele, val_ele)

    def _lyrics_popup_cb(self):
        def lyrics_popup(event: Event):
            track = self.track
            lyrics = track.get_tag_value_or_values('lyrics')
            title = f'Lyrics: {track.tag_artist} - {track.tag_album} - {track.tag_title}'
            text_kwargs = {'font': ('sans-serif', 14), 'read_only_style': False}
            BasicPopup(lyrics, title=title, multiline=True, text_kwargs=text_kwargs, bind_esc=True).run()

        return lyrics_popup

    # endregion


class SelectableSongFileFrame(SongFileFrame):
    # TODO: Add button/prompt to add a new tag?

    def __init__(self, *args, multi_select_cb: BindCallback = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._multi_select_cb = multi_select_cb
        self.to_delete = set()

    def reset_selection(self):
        self.to_delete.clear()
        for tag, rows in self._tag_id_rows_map.items():
            for row in rows:
                sel_box: CheckBox = row[1]
                sel_box.value = False

    def refresh(self):
        self.reset_selection()

    def _build_tag_row(self, tag_id: str, uniq_id: str, disp_name: str, value: Any) -> tuple[Text, CheckBox, ValueEle]:
        key_ele, val_ele = super()._build_tag_row(tag_id, uniq_id, disp_name, value)

        data = {'track_frame': self, 'tag_id': tag_id}
        sel_box = CheckBox('', disabled=self.disabled, data=data)
        sel_box.var_change_cb = self._box_toggled_callback(tag_id, sel_box, val_ele)

        binds = {'<Button-1>': sel_box.toggle_as_callback()}
        if multi_select_cb := self._multi_select_cb:
            binds['<Shift-Button-1>'] = multi_select_cb
            sel_box.bind('<Shift-Button-1>', multi_select_cb)

        for ele in (key_ele, val_ele):
            ele.data = data
            for bind_key, cb in binds.items():
                ele.bind(bind_key, cb)

        return (key_ele, sel_box, val_ele)

    def _box_toggled_callback(self, tag_id: str, sel_box: CheckBox, val_ele):
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

        return box_toggled_callback
