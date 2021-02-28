"""
Music manager GUI using PySimpleGUI.  WIP.

:author: Doug Skrypa
"""

import logging
from pathlib import Path
from typing import Callable, Dict, Tuple, Any, List

from PySimpleGUI import Window, Input, FolderBrowse, Listbox, theme, Popup, Text, Submit, Button, Element, Frame

from .base import GuiBase, event_handler
from .prompts import directory_prompt

__all__ = ['MusicManagerGui']
log = logging.getLogger(__name__)


class MusicManagerGui(GuiBase):
    def __init__(self):
        theme('SystemDefaultForReal')
        super().__init__(title='Music Manager', resizable=True)
        initial_layout = [
            Text('Music Manager'),
            Button('Select Album', enable_events=True, key='select_album'),
        ]
        self.set_layout([initial_layout])

    def _replace_layout(self, layout: List[List[Element]]):
        self.set_layout(layout)

    @event_handler('select_album')
    def select_album(self, event: str, data: Dict[str, Any]):
        if path := directory_prompt('Select Album'):
            log.debug(f'Selected album {path=}')
            file_names = [p.name for p in path.iterdir() if p.is_file()]

            self.set_layout([
                [Text(f'Album: {path}')],
                [Listbox(key='track_list', values=file_names, size=(40, len(file_names)), enable_events=True)]
            ])
