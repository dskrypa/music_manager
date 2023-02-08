"""
View that provides a diff between original Album/track info and submitted/proposed changes.
"""

from __future__ import annotations

import logging
from abc import ABC
from pathlib import Path
from typing import TYPE_CHECKING, Mapping, Any

from ds_tools.caching.decorators import cached_property
from ds_tools.output.prefix import LoggingPrefix
from tk_gui.enums import CallbackAction
from tk_gui.event_handling import button_handler
from tk_gui.options import GuiOptions
from tk_gui.popups import popup_error

from music.files.album import AlbumDir
from music_gui.elements.buttons import nav_button
from music_gui.elements.diff_frames import AlbumDiffFrame
from .base import BaseView

if TYPE_CHECKING:
    from tkinter import Event
    from tk_gui.elements import Button
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
        self,
        old_info: AlbumInfo,
        new_info: AlbumInfo,
        options: GuiOptions | Mapping[str, Any] = None,
        *,
        manually_edited: bool = True,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.album = self.old_info = old_info
        self.new_info = new_info
        if manually_edited and options is None:
            options = {'no_album_move': True}  # Default to True for manual edits, False for wiki edits
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

    @cached_property
    def next_button(self) -> Button | None:
        return nav_button('right')

    def get_inner_layout(self) -> Layout:
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

    @button_handler('next_view')
    def save_changes(self, event: Event = None, key=None) -> CallbackAction | None:
        from .album import AlbumView

        options = self.options.parse(self.window.results)
        dry_run = options['dry_run']
        album_dir = self.new_info.album_dir
        self._save_changes(album_dir, dry_run, options['add_genre'])
        if dry_run:
            return None

        album_dir.refresh()  # TODO: After edit, original tag values still persist...  Need to fix cache invalidation
        return self.set_next_view(view_cls=AlbumView, album=album_dir)

    def _save_changes(self, album_dir: AlbumDir, dry_run: bool, add_genre: bool):
        # TODO: Maybe add spinner
        image, data, mime_type = self.new_info.get_new_cover(force=True)

        file_info_map = self.new_info.get_file_info_map()
        for song_file, track_info in file_info_map.items():
            tags = track_info.tags()
            song_file.update_tags(tags, dry_run, add_genre=add_genre)
            if image is not None:
                song_file._set_cover_data(image, data, mime_type, dry_run)

            track_info.maybe_rename(song_file, dry_run)

        if new_album_path := self.album_diff_frame.new_album_path:  # returns None if self.options['no_album_move']
            self._move_album(album_dir, new_album_path, dry_run)

    def _move_album(self, album_dir: AlbumDir, new_album_path: Path, dry_run: bool):
        log.info(f'{LoggingPrefix(dry_run).move} {album_dir} -> {new_album_path.as_posix()}')
        if dry_run:
            return

        orig_parent_path = album_dir.path.parent
        try:
            album_dir.move(new_album_path)
        except OSError as e:
            popup_error(
                f'Unable to move album to {new_album_path.as_posix()!r}\n'
                'The configured output_base_dir may need to be updated.\n'
                f'Error: {e}'
            )
            return

        for path in (orig_parent_path, orig_parent_path.parent):
            log.log(19, f'Checking directory: {path}')
            if path.exists() and next(path.iterdir(), None) is None:
                log.log(19, f'Removing empty directory: {path}')
                try:
                    path.rmdir()
                except OSError as e:
                    popup_error(f'Unable to delete empty directory={path.as_posix()!r}:\n{e}')
                    break
