"""

"""

from __future__ import annotations

import logging
from abc import ABC
from typing import TYPE_CHECKING

from tk_gui.elements import HorizontalSeparator, Text, Frame, ScrollFrame
from tk_gui.event_handling import button_handler
from tk_gui.popups import popup_ok

from music_gui.elements.info_frames import AlbumInfoFrame, TrackInfoFrame
from music_gui.utils import AlbumIdentifier, get_album_info, with_separators
from .base import BaseView

if TYPE_CHECKING:
    from tkinter import Event
    from tk_gui.typing import Layout
    from music.manager.update import AlbumInfo

__all__ = ['AlbumView']
log = logging.getLogger(__name__)


class AlbumView(BaseView, ABC, title='Music Manager - Album Info'):
    window_kwargs = BaseView.window_kwargs | {'exit_on_esc': True}

    def __init__(self, album: AlbumIdentifier, **kwargs):
        super().__init__(**kwargs)
        self.album: AlbumInfo = get_album_info(album)
        self._track_frames: list[TrackInfoFrame] = []

    # region Layout Generation

    def _prepare_album_frame(self) -> Frame:
        return AlbumInfoFrame(self.album, disabled=True, anchor='n')

    def _prepare_track_frame(self) -> ScrollFrame:
        track_frames = [TrackInfoFrame(track, disabled=True) for track in self.album.tracks.values()]
        self._track_frames.extend(track_frames)
        tracks_frame = ScrollFrame(with_separators(track_frames, True), scroll_y=True)
        return tracks_frame

    def get_inner_layout(self) -> Layout:
        yield [Text('Album Path:'), Text(self.album.path.as_posix(), use_input_style=True, size=(150, 1))]
        yield [HorizontalSeparator()]
        yield [self._prepare_album_frame(), self._prepare_track_frame()]

    # endregion

    # region Event Handlers

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

    # endregion
