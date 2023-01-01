"""

"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from tk_gui.elements.menu import Menu, MenuGroup, MenuItem, MenuProperty, CloseWindow
from tk_gui.enums import CallbackAction
from tk_gui.popups import PickFolder, popup_input_invalid
from tk_gui.popups.about import AboutPopup
from tk_gui.views.view import View

from music.files.album import AlbumDir
from music.files.exceptions import InvalidAlbumDir
from music_gui.elements.menus import PathRightClickMenu
from music_gui.elements.track_info import TrackInfoFrame, SongFileFrame
from music_gui.utils import AlbumIdentifier, get_album_dir, get_album_info, with_separators

if TYPE_CHECKING:
    from tkinter import Event
    from tk_gui.typing import Layout
    from music.manager.update import AlbumInfo

__all__ = ['TrackInfoView', 'SongFileView']
log = logging.getLogger(__name__)


class MenuBar(Menu):
    with MenuGroup('File'):
        MenuItem('Open')
        CloseWindow()
    with MenuGroup('Help'):
        MenuItem('About', AboutPopup)


class TrackInfoView(View, title='Track Info'):
    window_kwargs = {'exit_on_esc': True}

    def __init__(self, album: AlbumIdentifier, **kwargs):
        super().__init__(**kwargs)
        self.album: AlbumInfo = get_album_info(album)

    def get_init_layout(self) -> Layout:
        return with_separators(map(TrackInfoFrame, self.album.tracks.values()), True)


class SongFileView(View, title='Track Info'):
    menu = MenuProperty(MenuBar)
    window_kwargs = {'exit_on_esc': True, 'right_click_menu': PathRightClickMenu()}

    def __init__(self, album: AlbumIdentifier, **kwargs):
        super().__init__(**kwargs)
        self.album: AlbumDir = get_album_dir(album)
        self._next_album = None

    def get_init_layout(self) -> Layout:
        yield [self.menu]
        yield from with_separators(map(SongFileFrame, self.album), True)

    @menu['File']['Open'].callback
    def pick_next_album(self, event: Event):
        if path := PickFolder(self.album.path.parent).run():
            self.window.take_focus()  # Can't seem to avoid it losing it perceptibly, but this brings it back faster
            log.debug(f'Selected album {path=}')
            try:
                self._next_album = AlbumDir(path)
            except InvalidAlbumDir as e:
                popup_input_invalid(str(e), logger=log)
            else:
                return CallbackAction.EXIT
        else:
            self.window.take_focus()

        return None

    def get_next_view(self) -> View | None:
        if album := self._next_album:
            return SongFileView(album)
        else:
            return None
