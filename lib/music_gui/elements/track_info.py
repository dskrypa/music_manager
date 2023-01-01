"""

"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Union, Iterator, Any, Iterable, Collection, Pattern

from PIL.Image import Image as PILImage, open as open_image
from requests import RequestException

from ds_tools.caching.decorators import cached_property
from ds_tools.fs.paths import get_user_cache_dir
from tk_gui.elements import Element, Image, Text, Input, ListBox, Button, HorizontalSeparator
from tk_gui.elements.frame import InteractiveFrame, InteractiveRowFrame
from tk_gui.elements.menu import Menu, MenuGroup
from tk_gui.elements.menu.items import CopySelection, PasteClipboard, GoogleSelection, SearchKpopFandom, SearchGenerasia
from tk_gui.elements.menu.items import FlipNameParts, ToUpperCase, ToTitleCase, ToLowerCase
from tk_gui.elements.menu.items import OpenFileLocation, OpenFile
from tk_gui.elements.rating import Rating
from tk_gui.elements.text import normalize_text_ele_widths, PathLink
from tk_gui.popups import popup_get_text
from tk_gui.views.view import View
from wiki_nodes.http import MediaWikiClient

from music.common.disco_entry import DiscoEntryType
from music.common.ratings import stars_from_256
from music.files.album import AlbumDir
from music.files.exceptions import TagNotFound
from music.files.track.track import SongFile
from music.manager.update import AlbumInfo, TrackInfo
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
        # TODO: Tags

    def get_basic_info_row(self):
        # TODO: right-click menu
        track = self.track
        tag_version = f'{track.tag_version} (lossless)' if track.lossless else track.tag_version
        link = PathLink(self.track.path, use_link_style=False, path_in_tooltip=True)
        return [
            Text('File:'), Text(self.file_name, size=(50, 1), link=link, use_input_style=True),
            Text('Length:'), Text(track.length_str, size=(6, 1), use_input_style=True),
            Text('Type:'), Text(tag_version, size=(20, 1), use_input_style=True),
        ]

    def get_metadata_row(self):
        # TODO: right-click menu
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
