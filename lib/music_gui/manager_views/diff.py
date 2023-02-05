"""
View that provides a diff between original Album/track info and submitted/proposed changes.
"""

from __future__ import annotations

import logging
from abc import ABC
from typing import TYPE_CHECKING, Mapping, Any

from ds_tools.caching.decorators import cached_property
from tk_gui.options import GuiOptions

from music_gui.elements.diff_frames import AlbumDiffFrame
from .base import BaseView

if TYPE_CHECKING:
    from tkinter import Event
    from tk_gui.typing import Layout
    from music.manager.update import AlbumInfo

__all__ = ['AlbumDiffView']
log = logging.getLogger(__name__)


class AlbumDiffView(BaseView, ABC, title='Music Manager - Album Info Diff'):
    window_kwargs = BaseView.window_kwargs | {'exit_on_esc': True}
    album: AlbumInfo
    old_info: AlbumInfo
    new_info: AlbumInfo

    def __init__(
        self, old_info: AlbumInfo, new_info: AlbumInfo, options: GuiOptions | Mapping[str, Any] = None, **kwargs
    ):
        super().__init__(**kwargs)
        self.album = self.old_info = old_info
        self.new_info = new_info
        self._options = options

    # region Layout Generation

    @cached_property
    def options(self) -> GuiOptions:
        gui_options = GuiOptions()
        gui_options.add_bool('dry_run', 'Dry Run', default=False)
        gui_options.add_bool(
            'add_genre', 'Add Genre', default=True, tooltip='Add any specified genres instead of replacing them'
        )
        # TODO: Trigger re-calculation of some fields immediately when these are checked/unchecked
        gui_options.add_bool('title_case', 'Title Case')
        gui_options.add_bool('no_album_move', 'Do Not Move Album')
        gui_options.add_bool('rename_in_place', 'Rename Album In-Place')
        gui_options.update(self._options)
        return gui_options

    @cached_property
    def album_diff_frame(self) -> AlbumDiffFrame:
        return AlbumDiffFrame(self.old_info, self.new_info, self.options, self.output_sorted_dir)

    def get_inner_layout(self) -> Layout:
        # TODO: Add submit/save "next" button
        yield [self.album_diff_frame]

    # endregion
