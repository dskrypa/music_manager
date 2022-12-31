"""

"""

from __future__ import annotations

import logging
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Union, Iterator, Any, Iterable, Collection, Pattern

from PIL.Image import Image as PILImage, open as open_image
from requests import RequestException

from ds_tools.caching.decorators import cached_property
from ds_tools.fs.paths import get_user_cache_dir
from tk_gui.elements import Element, Image, Text, Input, ListBox, Button
from tk_gui.elements.frame import InteractiveFrame, InteractiveRowFrame
from tk_gui.elements.menu import Menu, MenuGroup
from tk_gui.elements.menu.items import CopySelection, PasteClipboard, GoogleSelection, SearchKpopFandom, SearchGenerasia
from tk_gui.elements.menu.items import FlipNameParts, ToUpperCase, ToTitleCase, ToLowerCase
from tk_gui.elements.menu.items import OpenFileLocation, OpenFile
from tk_gui.elements.rating import Rating
from tk_gui.elements.text import normalize_text_ele_widths
from tk_gui.popups import popup_get_text
from tk_gui.views.view import View
from wiki_nodes.http import MediaWikiClient

from music.common.disco_entry import DiscoEntryType
from music.common.ratings import stars_from_256
from music.files.album import AlbumDir
from music.files.exceptions import TagNotFound
from music.manager.update import AlbumInfo, TrackInfo

if TYPE_CHECKING:
    from tkinter import Event
    from tk_gui.typing import Layout
    from music.files.track.track import SongFile

__all__ = []
log = logging.getLogger(__name__)


class PathRightClickMenu(Menu):
    CopySelection()
    with MenuGroup('Open'):
        OpenFileLocation()
        OpenFile()
    with MenuGroup('Search'):
        GoogleSelection()
        SearchKpopFandom()
        SearchGenerasia()


class TextRightClickMenu(Menu):
    CopySelection()
    PasteClipboard()
    with MenuGroup('Search'):
        GoogleSelection()
        SearchKpopFandom()
        SearchGenerasia()


class EditableTextRightClickMenu(TextRightClickMenu):
    CopySelection()
    PasteClipboard()
    with MenuGroup('Search'):
        GoogleSelection()
        SearchKpopFandom()
        SearchGenerasia()
    with MenuGroup('Update'):
        FlipNameParts()
        ToLowerCase()
        ToUpperCase()
        ToTitleCase()


class EditableListBox(InteractiveRowFrame):
    def __init__(
        self,
        values: Collection[str],
        key: str,
        add_title: str,
        add_prompt: str,
        list_width: int = 30,
        **kwargs,
    ):
        kwargs.setdefault('pad', (0, 0))
        super().__init__(**kwargs)
        self.__key: str = key
        self._values = values
        self._list_width = list_width
        self.add_title = add_title
        self.add_prompt = add_prompt

    @cached_property
    def list_box(self) -> ListBox:
        values = self._values
        kwargs = {
            'size': (self._list_width, len(values)),
            'tooltip': 'Unselected items will not be saved',
            'pad': (4, 0),
            'border': 2,
        }
        return ListBox(values, default=values, disabled=self.disabled, scroll_y=False, key=self.__key, **kwargs)

    @cached_property
    def button(self) -> Button:
        return Button(
            'Add...',
            key=self.__key.replace('val::', 'add::', 1),
            pad=(0, 0),
            visible=not self.disabled,
            cb=self.add_value,
        )

    def add_value(self, event: Event):
        if value := popup_get_text(self.add_prompt, self.add_title, bind_esc=True):
            self.list_box.append_choice(value, True)

    @property
    def elements(self) -> tuple[Element, ...]:
        return self.list_box, self.button

    def enable(self):
        if not self.disabled:
            return
        self.button.show()
        self.list_box.enable()
        self.disabled = False

    def disable(self):
        if self.disabled:
            return
        self.button.hide()
        self.list_box.disable()
        self.disabled = True


class TrackInfoFrame(InteractiveFrame):
    track_info: TrackInfo

    def __init__(self, track: TrackInfo | SongFile, **kwargs):
        if not isinstance(track, TrackInfo):
            track = TrackInfo.from_file(track)
        self.track_info = track
        super().__init__(**kwargs)

    def get_custom_layout(self) -> Layout:
        return normalize_text_ele_widths([row for row in self.build_info_rows()])  # noqa

    @cached_property
    def path_str(self) -> str:
        return self.track_info.path.as_posix()

    @cached_property
    def file_name(self) -> str:
        return self.track_info.path.name

    def key_for(self, type: str, field: str, suffix: str = None) -> str:  # noqa
        if suffix:
            return f'{type}::{self.path_str}::{field}::{suffix}'
        else:
            return f'{type}::{self.path_str}::{field}'

    def _val_key(self, key: str, suffix: str = None) -> str:
        return self.key_for('val', key, suffix)

    def _key_text(self, key: str, suffix: str = None) -> Text:
        return Text(key.replace('_', ' ').title(), key=self.key_for('tag', key, suffix))

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

    def _rating_row(self, key: str, value, suffix: str = None):
        row = [
            self._key_text(key, suffix),
            Rating(value, key=self._val_key(key, suffix), show_value=True, pad=(0, 0), disabled=self.disabled),
        ]
        return row


class TrackInfoView(View, title='Track Info'):
    window_kwargs = {'exit_on_esc': True}

    def __init__(self, album: AlbumInfo | AlbumDir | Path | str, **kwargs):
        super().__init__(**kwargs)
        if isinstance(album, AlbumDir):
            album = AlbumInfo.from_album_dir(album)
        elif isinstance(album, (Path, str)):
            album = AlbumInfo.from_path(album)
        self.album: AlbumInfo = album

    def get_init_layout(self) -> Layout:
        return [[TrackInfoFrame(track)] for track in self.album.tracks.values()]


if __name__ == '__main__':
    TrackInfoView('C:/Users/dskry/etc/music_flac/kpop_2022-12-30/BIBI/BIBI [2019.05.15] BINU [FLAC-16bit-44.1kHz]').run()
