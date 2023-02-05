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
        gui_options.add_bool('title_case', 'Title Case')
        gui_options.add_bool('no_album_move', 'Do Not Move Album')
        gui_options.add_bool('rename_in_place', 'Rename Album In-Place')
        gui_options.update(self._options)
        return gui_options

    @cached_property
    def album_diff_frame(self) -> AlbumDiffFrame:
        return AlbumDiffFrame(
            self.old_info,
            self.new_info,
            output_sorted_dir=self.output_sorted_dir,
            options=self.options,
            update_options_cb=self.update_options,
        )

    def get_inner_layout(self) -> Layout:
        # TODO: Add submit/save "next" button + handling for it
        yield [self.album_diff_frame]

    # endregion

    def update_options(self, *args):
        old_options = dict(self.options.items())
        new_options = self.options.parse(self.window.results)
        changed = {k: v for k, v in new_options.items() if v != old_options[k]}
        if 'add_genre' in changed or 'title_case' in changed:
            return self.set_next_view(old_info=self.old_info, new_info=self.new_info, options=self.options)

        album_diff_frame = self.album_diff_frame
        album_diff_frame.update_option_states(self.window)  # noqa
        rename_ele, no_change_ele = album_diff_frame.path_diff_eles
        if new_album_path := album_diff_frame.new_album_path:
            new_album_path = new_album_path.as_posix()
        else:
            new_album_path = ''
        rename_ele.rows[-1].elements[-1].update(new_album_path)

        if 'no_album_move' in changed:
            if changed['no_album_move']:
                rename_ele.hide()
                no_change_ele.show()
            else:
                rename_ele.show()
                no_change_ele.hide()
