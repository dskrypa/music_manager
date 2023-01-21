"""

"""

from __future__ import annotations

import logging
from abc import ABC
from typing import TYPE_CHECKING, Type

from ds_tools.caching.decorators import cached_property
from ds_tools.output.prefix import LoggingPrefix
from tk_gui.elements import HorizontalSeparator, Button, Text, Frame, ScrollFrame
from tk_gui.elements.menu import Menu, MenuGroup, MenuItem, MenuProperty, CloseWindow
from tk_gui.enums import CallbackAction
from tk_gui.popups import popup_input_invalid, pick_folder_popup, BoolPopup, popup_ok
from tk_gui.popups.about import AboutPopup
from tk_gui.views.view import View
from tk_gui.options import GuiOptions

from music.files.track.track import SongFile
from music.files.album import AlbumDir
from music.files.exceptions import InvalidAlbumDir
from music_gui.elements.menus import FullRightClickMenu, MusicManagerMenuBar
from music_gui.elements.track_info import TrackInfoFrame, AlbumInfoFrame
from music_gui.utils import AlbumIdentifier, get_album_dir, get_album_info, with_separators, call_timer
from .base import BaseView

if TYPE_CHECKING:
    from tkinter import Event, BaseWidget
    from tk_gui.typing import Layout
    from music.manager.update import AlbumInfo

__all__ = []
log = logging.getLogger(__name__)


class AlbumView(BaseView, ABC, title='Album Info'):
    menu = MenuProperty(MusicManagerMenuBar)
    window_kwargs = {'exit_on_esc': True, 'right_click_menu': FullRightClickMenu()}
    album: AlbumInfo | AlbumDir

    def __init__(self, album: AlbumIdentifier, **kwargs):
        super().__init__(**kwargs)
        self.album: AlbumInfo = get_album_info(album)
        self._track_frames: list[TrackInfoFrame] = []

    @menu['File']['Open'].callback
    def pick_next_album(self, event: Event):
        if path := pick_folder_popup(self.album.path.parent, 'Pick Album Directory', parent=self.window):
            log.debug(f'Selected album {path=}')
            try:
                return self.set_next_view(AlbumDir(path))
            except InvalidAlbumDir as e:
                popup_input_invalid(str(e), logger=log)

        return None

    def get_pre_window_layout(self) -> Layout:
        yield [self.menu]

    def _prepare_album_frame(self) -> Frame:
        return AlbumInfoFrame(self.album)

    def _prepare_track_frame(self) -> ScrollFrame:
        track_frames = [TrackInfoFrame(track, disabled=True) for track in self.album.tracks.values()]
        self._track_frames.extend(track_frames)
        tracks_frame = ScrollFrame(with_separators(track_frames, True), scroll_y=True)
        return tracks_frame

    def get_post_window_layout(self) -> Layout:
        yield [self._prepare_album_frame(), self._prepare_track_frame()]
