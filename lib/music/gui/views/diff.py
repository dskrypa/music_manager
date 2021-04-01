"""
Gui Views

:author: Doug Skrypa
"""

import logging
from dataclasses import fields
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, Union

from PySimpleGUI import Text, Button, Column, Element, Checkbox, Frame, Submit, Input

from ...files.album import AlbumDir
from ...files.exceptions import InvalidAlbumDir
from ...manager.update import AlbumInfo, TrackInfo
from .base import ViewManager, event_handler
from .main import MainView

__all__ = ['AlbumDiffView']
log = logging.getLogger(__name__)


class AlbumDiffView(MainView, view_name='album_diff'):
    def __init__(self, mgr: 'ViewManager', album_info: AlbumInfo):
        super().__init__(mgr)
        self.album_info = album_info

    def get_render_args(self) -> tuple[list[list[Element]], dict[str, Any]]:
        layout, kwargs = super().get_render_args()
        # # TODO: Make dry_run not default
        # # TODO: Implement gui-based diff
        # # TODO: Input sanitization/normalization
        # album_info.update_and_move(self.album, None, dry_run=True)

        return layout, kwargs
