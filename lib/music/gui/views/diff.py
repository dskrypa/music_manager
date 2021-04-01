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


class AlbumDiffView(BaseView, view_name='album_diff'):
    def __init__(self, mgr: 'ViewManager', album_info: AlbumInfo):
        super().__init__(mgr)
        self.album_info = album_info

    def get_render_args(self) -> tuple[list[list[Element]], dict[str, Any]]:
        layout, kwargs = super().get_render_args()
        return layout, kwargs
