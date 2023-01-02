"""

"""

from __future__ import annotations

import logging
from abc import ABC
from typing import TYPE_CHECKING

from tk_gui.elements import Element, HorizontalSeparator, CheckBox
from tk_gui.elements.menu import Menu, MenuGroup, MenuItem, MenuProperty, CloseWindow
from tk_gui.enums import CallbackAction
from tk_gui.popups import popup_input_invalid, pick_folder_popup
from tk_gui.popups.about import AboutPopup
from tk_gui.views.view import View

from music.files.album import AlbumDir
from music.files.exceptions import InvalidAlbumDir
from music_gui.elements.menus import PathRightClickMenu
from music_gui.elements.track_info import TrackInfoFrame, SongFileFrame, SelectableSongFileFrame
from music_gui.utils import AlbumIdentifier, get_album_dir, get_album_info, with_separators

if TYPE_CHECKING:
    from tkinter import Event, BaseWidget
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


class BaseTrackView(View, ABC, title='Track Info'):
    menu = MenuProperty(MenuBar)
    window_kwargs = {'exit_on_esc': True, 'right_click_menu': PathRightClickMenu(), 'scroll_y': True}
    _next_album = None
    album: AlbumInfo | AlbumDir

    def get_pre_window_layout(self) -> Layout:
        yield [self.menu]

    @menu['File']['Open'].callback
    def pick_next_album(self, event: Event):
        if path := pick_folder_popup(self.album.path.parent, 'Pick Album Directory', parent=self.window):
            log.debug(f'Selected album {path=}')
            try:
                self._next_album = AlbumDir(path)
            except InvalidAlbumDir as e:
                popup_input_invalid(str(e), logger=log)
            else:
                return CallbackAction.EXIT

        return None

    def get_next_view(self) -> View | None:
        if album := self._next_album:
            return self.__class__(album)  # noqa
        else:
            return None


class TrackInfoView(BaseTrackView):
    def __init__(self, album: AlbumIdentifier, **kwargs):
        super().__init__(**kwargs)
        self.album: AlbumInfo = get_album_info(album)

    def get_post_window_layout(self) -> Layout:
        yield from with_separators(map(TrackInfoFrame, self.album.tracks.values()), True)


class SongFileView(BaseTrackView):
    def __init__(self, album: AlbumIdentifier, **kwargs):
        super().__init__(**kwargs)
        self.album: AlbumDir = get_album_dir(album)

    def get_post_window_layout(self) -> Layout:
        yield from with_separators(map(SongFileFrame, self.album), True)


class SelectableSongFileView(SongFileView):
    def __init__(self, album: AlbumIdentifier, **kwargs):
        super().__init__(album, **kwargs)
        self._track_frames: list[SelectableSongFileFrame] = []

    def multi_select_cb(self, event: Event):
        try:
            element = self.window.widget_element_map[event.widget]
        except (AttributeError, KeyError):
            return
        try:
            track_frame: SelectableSongFileFrame = element.data['track_frame']  # noqa
            tag_id = element.data['tag_id']  # noqa
        except (TypeError, KeyError):
            return
        try:
            target_value = next(not row[1].value for row in track_frame.get_tag_rows(tag_id) if element in row)
        except StopIteration:
            return

        # log.debug(f'Setting all {tag_id=} values to {target_value=}')
        for frame in self._track_frames:
            for row in frame.get_tag_rows(tag_id):
                if (row_box := row[1]) is not element:
                    # If the element that was clicked was the checkbox itself, then that element needs to be skipped
                    # here.  The bind callback is executed before the normal checkbox action, which is to toggle its
                    # value from whatever it is at the time that that happens.  This means we cannot set the target
                    # value for the element that was clicked, otherwise the normal click action would just reset it
                    # to the current value.
                    row_box.value = target_value  # noqa

    def get_post_window_layout(self) -> Layout:
        for i, track in enumerate(self.album):
            frame = SelectableSongFileFrame(track, multi_select_cb=self.multi_select_cb)
            self._track_frames.append(frame)
            if i:
                yield [HorizontalSeparator()]
            yield [frame]
