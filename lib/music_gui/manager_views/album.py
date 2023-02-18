"""
View that separates common album fields from common fields that are usually different between tracks.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Iterator

from ds_tools.caching.decorators import cached_property

from tk_gui.elements import HorizontalSeparator, Text, ScrollFrame, Button
from tk_gui.event_handling import button_handler
from tk_gui.popups import popup_ok

from music_gui.elements.helpers import IText, nav_button
from music_gui.elements.info_frames import AlbumInfoFrame, TrackInfoFrame
from music_gui.utils import AlbumIdentifier, get_album_info, with_separators
from .base import BaseView

if TYPE_CHECKING:
    from tkinter import Event
    from tk_gui.enums import CallbackAction
    from tk_gui.typing import Layout
    from music.manager.update import AlbumInfo

__all__ = ['AlbumView']
log = logging.getLogger(__name__)


class AlbumView(BaseView, title='Music Manager - Album Info'):
    window_kwargs = BaseView.window_kwargs | {'exit_on_esc': True}

    def __init__(self, album: AlbumIdentifier, *, editable: bool = False, edited: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.album: AlbumInfo = get_album_info(album)
        self._track_frames: list[TrackInfoFrame] = []
        self.editing = editable
        self.edited = edited

    # region Layout Generation

    @cached_property
    def album_info_frame(self) -> AlbumInfoFrame:
        return AlbumInfoFrame(self.album, disabled=not self.editing, anchor='n')

    @cached_property
    def next_button(self) -> Button | None:
        return nav_button('right', visible=self.editing, tooltip='Review & Save Changes')

    def _prepare_track_frames(self) -> ScrollFrame:
        track_frames = [TrackInfoFrame(track, disabled=True) for track in self.album.tracks.values()]
        self._track_frames.extend(track_frames)
        tracks_frame = ScrollFrame(with_separators(track_frames, True), scroll_y=True, fill_y=True)
        return tracks_frame

    def get_inner_layout(self) -> Layout:
        yield [Text('Album Path:'), IText(self.album.path, size=(150, 1))]
        yield [HorizontalSeparator()]
        yield [self.album_info_frame, self._prepare_track_frames()]

    # endregion

    def _get_info_diff(self) -> tuple[bool, AlbumInfo, AlbumInfo]:
        old_info = self.album.clean(self.edited)
        new_info = self.album.copy()

        if album_changes := self.album_info_frame.get_modified():
            new_info.update_from_old_new_tuples(album_changes)

        track_info_modifications = [(tf.track_info, tf.get_modified()) for tf in self._track_frames]
        any_genres_modified = 'genre' in album_changes or any('genre' in mod for _, mod in track_info_modifications)

        for track_info, modified in track_info_modifications:
            if any_genres_modified and 'genre' not in modified:
                modified['genre'] = (old_info.get_track(track_info).get_genre_set(), set())
            if modified:
                new_info.get_track(track_info).update_from_old_new_tuples(modified)

        return old_info != new_info, old_info, new_info

    def _iter_frames(self) -> Iterator[AlbumInfoFrame | TrackInfoFrame]:
        yield self.album_info_frame
        yield from self._track_frames

    # region Event Handlers

    @button_handler('clean_and_add_bpm')
    def clean_and_add_bpm(self, event: Event, key=None):
        popup_ok(f'Not implemented yet: {key}')  # TODO

    @button_handler('view_all_tags')
    def view_all_tags(self, event: Event, key=None) -> CallbackAction:
        from .tracks import SelectableSongFileView

        return self.set_next_view(self.album, view_cls=SelectableSongFileView)

    @button_handler('edit_album', 'cancel')
    def toggle_edit_mode(self, event: Event, key=None) -> CallbackAction | None:
        if self.edited and key == 'cancel':
            return self.set_next_view(album=self.album.clean(True))

        if disable := key != 'edit_album':
            if self._get_info_diff()[0]:
                for frame in self._iter_frames():
                    frame.reset_tag_values()

        self.next_button.toggle_visibility(not disable)
        for frame in self._iter_frames():
            frame.toggle_enabled(disable)

        return None

    @button_handler('save', 'next_view')
    def save_changes(self, event: Event, key=None) -> CallbackAction | None:
        from .diff import AlbumDiffView

        changed, old_info, new_info = self._get_info_diff()
        if changed:
            return self.set_next_view(view_cls=AlbumDiffView, old_info=old_info, new_info=new_info)
        else:
            popup_ok('No changes were made - there is nothing to save')
            return

    @button_handler('wiki_update')
    def wiki_update(self, event: Event, key=None):
        from .wiki_update import WikiUpdateView

        return self.set_next_view(self.album, view_cls=WikiUpdateView)

    @button_handler('sync_ratings_from', 'sync_ratings_to')
    def sync_ratings_from(self, event: Event, key=None):
        popup_ok(f'Not implemented yet: {key}')  # TODO

    @button_handler('copy_tags_from')
    def copy_tags_from(self, event: Event, key=None):
        popup_ok(f'Not implemented yet: {key}')  # TODO

    # endregion
