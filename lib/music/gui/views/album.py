"""
Gui Views

:author: Doug Skrypa
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import fields
from pathlib import Path
from functools import partial, update_wrapper
from multiprocessing import Pool
from typing import TYPE_CHECKING, Any, Optional, Union

from PySimpleGUI import Text, Button, Column, Element, Checkbox, Frame, Submit, Input
from PySimpleGUI import popup_ok, theme

from ds_tools.logging import init_logging, ENTRY_FMT_DETAILED_PID
from ...common.utils import aubio_installed
from ...files.album import AlbumDir
from ...files.exceptions import InvalidAlbumDir
from ...manager.file_update import _add_bpm
from ...manager.update import AlbumInfo, TrackInfo
from ..prompts import directory_prompt, popup_input_invalid
from ..progress import ProgressTracker
from .base import GuiView, ViewManager, event_handler, BaseView
from .formatting import AlbumBlock

__all__ = []
log = logging.getLogger(__name__)


class AlbumView(BaseView, view_name='album'):
    def __init__(self, mgr: 'ViewManager', album: AlbumDir):
        super().__init__(mgr)
        self.album = album
        self.album_block: Optional[AlbumBlock] = None
        self.editing = False

    def get_render_args(self) -> tuple[list[list[Element]], dict[str, Any]]:
        layout, kwargs = super().get_render_args()
        self.album_block = AlbumBlock(self, self.album)
        layout.extend(self.album_block.as_rows(False))
        return layout, kwargs

    # def render(self):
    #     self.album_block = AlbumBlock(self.gui, self.album)
    #     self.gui.set_layout(list(self.album_block.as_rows(False)))

    @event_handler
    def all_tags(self, event: str, data: dict[str, Any]):
        from .tags import AllTagsView
        AllTagsView(self.mgr, self.album).render()

    @event_handler
    def cancel(self, event: str, data: dict[str, Any]):
        self.render()

    @event_handler
    def edit(self, event: str, data: dict[str, Any]):
        if not self.album_block.editing:
            self.album_block.toggle_editing()

    @event_handler
    def save(self, event: str, data: dict[str, Any]):
        from .diff import AlbumDiffView
        self.album_block.toggle_editing()
        info_dict = {}
        track_info_dict = {}
        info_fields = {f.name: f for f in fields(AlbumInfo)} | {f.name: f for f in fields(TrackInfo)}

        for data_key, value in data.items():
            try:
                key_type, obj, key = data_key.split('::')  # val::album::key
            except Exception:
                pass
            else:
                if key_type == 'val':
                    try:
                        value = info_fields[key].type(value)
                    except (KeyError, TypeError, ValueError):
                        pass
                    if obj == 'album':
                        info_dict[key] = value
                    else:
                        track_info_dict.setdefault(obj, {})[key] = value
        info_dict['tracks'] = track_info_dict

        album_info = AlbumInfo.from_dict(info_dict)
        AlbumDiffView(self.mgr, album_info).render()
