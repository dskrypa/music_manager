"""
Gui Views

:author: Doug Skrypa
"""

import logging
from typing import Any, Optional

from PySimpleGUI import Button, Element, popup_ok

from ...files.album import AlbumDir
from ...files.exceptions import InvalidAlbumDir
from ..prompts import directory_prompt, popup_input_invalid
from .base import ViewManager, event_handler, BaseView

__all__ = ['MainView']
log = logging.getLogger(__name__)


class MainView(BaseView, view_name='main'):
    def __init__(self, mgr: 'ViewManager'):
        super().__init__(mgr)
        self.menu = [
            ['File', ['Open', 'Exit']],
            ['Actions', ['Clean', 'Edit', 'Wiki Update']],
            ['Help', ['About']],
        ]

    def get_render_args(self) -> tuple[list[list[Element]], dict[str, Any]]:
        layout, kwargs = super().get_render_args()
        if self.__class__ is MainView:
            layout.append([Button('Select Album', enable_events=True, key='select_album')])
        return layout, kwargs

    def get_album_selection(self, new: bool = False) -> Optional[AlbumDir]:
        if not new:
            if album := getattr(self, 'album', None):
                return album

        if path := directory_prompt('Select Album'):
            log.debug(f'Selected album {path=}')
            try:
                return AlbumDir(path)
            except InvalidAlbumDir as e:
                popup_input_invalid(str(e))

        return None

    @event_handler('Open')  # noqa
    def select_album(self, event: str, data: dict[str, Any]):
        if album := self.get_album_selection(True):
            from .album import AlbumView

            return AlbumView(self.mgr, album)

    @event_handler('Edit')  # noqa
    def edit(self, event: str, data: dict[str, Any]):
        if album := self.get_album_selection():
            from .album import AlbumView

            return AlbumView(self.mgr, album, getattr(self, 'album_block', None), editing=True)

    @event_handler('Clean')  # noqa
    def clean(self, event: str, data: dict[str, Any]):
        if album := self.get_album_selection():
            from .clean import CleanView

            return CleanView(self.mgr, album)

    @event_handler('Wiki Update')  # noqa
    def wiki_update(self, event: str, data: dict[str, Any]):
        popup_ok('Wiki update is not implemented yet.')
