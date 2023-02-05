"""

"""

from __future__ import annotations

import logging
from abc import ABC
from typing import TYPE_CHECKING

from ds_tools.caching.decorators import cached_property
# from ds_tools.output.repr import rich_repr
from tk_gui.elements import HorizontalSeparator, Text, ScrollFrame
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
        self.editing = False

    # region Layout Generation

    @cached_property
    def album_info_frame(self) -> AlbumInfoFrame:
        return AlbumInfoFrame(self.album, disabled=True, anchor='n')

    def _prepare_track_frames(self) -> ScrollFrame:
        track_frames = [TrackInfoFrame(track, disabled=True) for track in self.album.tracks.values()]
        self._track_frames.extend(track_frames)
        tracks_frame = ScrollFrame(with_separators(track_frames, True), scroll_y=True)
        return tracks_frame

    def get_inner_layout(self) -> Layout:
        yield [Text('Album Path:'), Text(self.album.path.as_posix(), use_input_style=True, size=(150, 1))]
        yield [HorizontalSeparator()]
        yield [self.album_info_frame, self._prepare_track_frames()]

    # endregion

    # region Event Handlers

    @button_handler('clean_and_add_bpm')
    def clean_and_add_bpm(self, event: Event, key=None):
        popup_ok(f'Not implemented yet: {key}')

    @button_handler('view_all_tags')
    def view_all_tags(self, event: Event, key=None):
        from .tracks import SelectableSongFileView

        return self.set_next_view(self.album, view_cls=SelectableSongFileView)

    @button_handler('edit_album', 'cancel')
    def toggle_edit_mode(self, event: Event, key=None):
        # TODO: Reset edits on cancel?
        if key == 'edit_album':
            self.album_info_frame.enable()
            for track_frame in self._track_frames:
                track_frame.enable()
        else:
            self.album_info_frame.disable()
            for track_frame in self._track_frames:
                track_frame.disable()

    @button_handler('save')
    def save_changes(self, event: Event, key=None):
        from .diff import AlbumDiffView

        old_info = self.album
        new_info = old_info.copy()
        any_changes = False  # TODO: Implement __eq__ for AlbumInfo to skip the tracking here
        if album_changes := self.album_info_frame.get_modified():
            any_changes = True
            # TODO: Re-calculate numbered_type if type/number changed
            new_info.update_from_old_new_tuples(album_changes)

        for tf in self._track_frames:
            if modified := tf.get_modified():
                any_changes = True
                new_info.tracks[tf.track_info.path.as_posix()].update_from_old_new_tuples(modified)

        if any_changes:
            return self.set_next_view(view_cls=AlbumDiffView, old_info=old_info, new_info=new_info)
        else:
            popup_ok('No changes were made - there is nothing to save')
            return

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
