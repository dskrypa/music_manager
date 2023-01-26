"""

"""

from __future__ import annotations

import logging
from abc import ABC
from typing import TYPE_CHECKING

from tk_gui.elements import HorizontalSeparator, Text, Frame, ScrollFrame
from tk_gui.elements.menu import MenuProperty
from tk_gui.event_handling import button_handler
from tk_gui.popups import popup_input_invalid, pick_folder_popup, popup_ok
from tk_gui.views.view import View

from music.files.album import AlbumDir
from music.files.exceptions import InvalidAlbumDir
from music_gui.elements.menus import FullRightClickMenu, MusicManagerMenuBar
from music_gui.elements.info_frames import AlbumInfoFrame, TrackInfoFrame
from music_gui.utils import AlbumIdentifier, get_album_info, with_separators

if TYPE_CHECKING:
    from tkinter import Event
    from tk_gui.typing import Layout
    from music.manager.update import AlbumInfo

__all__ = ['AlbumView']
log = logging.getLogger(__name__)


class AlbumView(View, ABC, title='Album Info'):
    menu = MenuProperty(MusicManagerMenuBar)
    window_kwargs = {'exit_on_esc': True, 'right_click_menu': FullRightClickMenu()}
    album: AlbumInfo | AlbumDir

    def __init__(self, album: AlbumIdentifier, **kwargs):
        super().__init__(**kwargs)
        self.album: AlbumInfo = get_album_info(album)
        self._track_frames: list[TrackInfoFrame] = []

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__}[{self.title}][{self.album.path.as_posix()}]>'

    # region Layout Generation

    def get_pre_window_layout(self) -> Layout:
        yield [self.menu]

    def _prepare_album_frame(self) -> Frame:
        return AlbumInfoFrame(self.album, disabled=True, anchor='n')

    def _prepare_track_frame(self) -> ScrollFrame:
        track_frames = [TrackInfoFrame(track, disabled=True) for track in self.album.tracks.values()]
        self._track_frames.extend(track_frames)
        tracks_frame = ScrollFrame(with_separators(track_frames, True), scroll_y=True)
        return tracks_frame

    def get_post_window_layout(self) -> Layout:
        yield [Text('Album Path:'), Text(self.album.path.as_posix(), use_input_style=True, size=(150, 1))]
        yield [HorizontalSeparator()]
        yield [self._prepare_album_frame(), self._prepare_track_frame()]

    # endregion

    # region Event Handlers

    @button_handler('open')
    @menu['File']['Open'].callback
    def pick_next_album(self, event: Event, key=None):
        if path := pick_folder_popup(self.album.path.parent, 'Pick Album Directory', parent=self.window):
            log.debug(f'Selected album {path=}')
            try:
                return self.set_next_view(AlbumDir(path))
            except InvalidAlbumDir as e:
                popup_input_invalid(str(e), logger=log)

        return None

    @button_handler('clean_and_add_bpm')
    def clean_and_add_bpm(self, event: Event, key=None):
        popup_ok(f'Not implemented yet: {key}')

    @button_handler('view_all_tags')
    def view_all_tags(self, event: Event, key=None):
        from .tracks import SelectableSongFileView

        # TODO: Add way to go back to this view
        return self.set_next_view(self.album, view_cls=SelectableSongFileView)

    @button_handler('edit_album')
    def edit_album(self, event: Event, key=None):
        popup_ok(f'Not implemented yet: {key}')

    @button_handler('wiki_update')
    def wiki_update(self, event: Event, key=None):
        popup_ok(f'Not implemented yet: {key}')

    @button_handler('sync_ratings_from', 'sync_ratings_to')
    def sync_ratings_from(self, event: Event, key=None):
        popup_ok(f'Not implemented yet: {key}')

    @button_handler('copy_tags_from')
    def copy_tags_from(self, event: Event, key=None):
        popup_ok(f'Not implemented yet: {key}')

    # @event_handler(BindEvent.LEFT_CLICK.event)
    # def _handle_left_click(self, event: Event):
    #     from tk_gui.event_handling import log_widget_data
    #
    #     log_widget_data(self.window, event, parent=True)

    # endregion
