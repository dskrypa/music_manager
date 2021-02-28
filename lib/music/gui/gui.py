"""
Music manager GUI using PySimpleGUI.  WIP.

:author: Doug Skrypa
"""

import logging
from pathlib import Path
from typing import Callable, Dict, Tuple, Any

from PySimpleGUI import Window, Input, FolderBrowse, Listbox, theme, Popup, Text, Submit

from .base import GuiBase, event_handler

__all__ = ['MusicManagerGui']
log = logging.getLogger(__name__)


class MusicManagerGui(GuiBase):
    def __init__(self):
        theme('SystemDefaultForReal')
        self.window = Window(
            title='Music Manager',
            layout=self.layout,
            resizable=True,
        )

    @property
    def layout(self):
        ui_elements = [  # => Column[Row[], Row[], ...]
            [
                Text('Album:'),
                Input(key='album_dir', enable_events=True, size=(150, 1)),
                # Input(key='album_dir', size=(150, 1)),
                # sg.Input(key='album_dir', enable_events=True),
                FolderBrowse('Browse'),
                Submit(key='submit_album_dir'),
            ],
            [
                Listbox(key='track_list', values=[], enable_events=True, size=(40, 20)),
            ]
        ]
        return ui_elements

    @event_handler('album_dir', 'submit_album_dir')
    def album_dir_picked(self, event: str, data: Dict[str, Any]):
        path = Path(data['album_dir']).resolve()
        if path.is_dir():
            self.window['track_list'].update([p.name for p in path.iterdir() if p.is_file()])
        elif event == 'submit_album_dir':
            self.window['track_list'].update([])
            Popup(f'Invalid directory: {path}', title='Invalid directory')
