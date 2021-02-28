"""
Music manager GUI using PySimpleGUI.  WIP.

:author: Doug Skrypa
"""

import logging
from pathlib import Path
from typing import Callable, Dict, Tuple, Any

from PySimpleGUI import Window, Input, FolderBrowse, Listbox

from .base import GuiBase, event_handler

__all__ = ['MusicManagerGui']
log = logging.getLogger(__name__)


class MusicManagerGui(GuiBase):
    def __init__(self):
        self.window = Window(title='Music Manager', layout=self.layout, margins=(800, 500))

    @property
    def layout(self):
        ui_elements = [  # => Column[Row[], Row[], ...]
            [
                Input(key='album_dir', enable_events=True, size=(150, 1)),
                # sg.Input(key='album_dir', enable_events=True),
                FolderBrowse('Browse for Album'),
            ],
            [
                Listbox(key='track_list', values=[], enable_events=True, size=(40, 20)),
            ]
        ]
        return ui_elements

    @event_handler('album_dir')
    def album_dir_picked(self, data: Dict[str, Any]):
        path = Path(data['album_dir']).resolve()
        self.window['track_list'].update([p.name for p in path.iterdir() if p.is_file()])
