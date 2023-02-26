"""
View that provides a diff between original Album/track info and submitted/proposed changes.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Mapping, Any

from ds_tools.caching.decorators import cached_property
from ds_tools.output.prefix import LoggingPrefix
from tk_gui.enums import CallbackAction
from tk_gui.event_handling import button_handler
from tk_gui.options import GuiOptions, BoolOption
from tk_gui.popups import popup_error

from music.files.album import AlbumDir
from music_gui.elements.diff_frames import AlbumDiffFrame
from music_gui.elements.helpers import nav_button
from .base import BaseView

if TYPE_CHECKING:
    from tkinter import Event
    from tk_gui.elements import Button
    from tk_gui.typing import Layout
    from tk_gui.views.view import ViewSpec
    from music.manager.update import AlbumInfo

__all__ = ['AlbumDiffView']
log = logging.getLogger(__name__)


class AlbumDiffView(BaseView, title='Music Manager - Album Info Diff'):
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
            options = {
                'no_album_move': True,  # Default to True for manual edits, False for wiki edits
                'repl_genres': True,    # Manual edits expect the submitted values to be used as seen
            }
        self._options = options

    # region Layout Generation

    @cached_property
    def options(self) -> GuiOptions:
        options = [
            BoolOption('dry_run', 'Dry Run'),
            BoolOption('repl_genres', 'Replace Genres', tooltip='Specified genres should replace existing ones'),
            BoolOption('title_case', 'Title Case'),
            BoolOption('no_album_move', 'Do Not Move Album'),
            BoolOption('rename_in_place', 'Rename Album In-Place'),
        ]
        gui_options = GuiOptions([options])
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
            show_edit=self.prev_view_name == 'WikiUpdateView',
        )

    @cached_property
    def back_button(self) -> Button | None:
        if (prev_view_name := self.prev_view_name) == 'WikiUpdateView':
            tooltip = 'Return to wiki match options'
        elif prev_view_name == 'AlbumView':
            tooltip = 'Edit album'
        else:
            tooltip = None
        return nav_button('left', tooltip=tooltip)

    @cached_property
    def next_button(self) -> Button | None:
        return nav_button('right', tooltip='Save Changes')

    def get_inner_layout(self) -> Layout:
        yield [self.album_diff_frame]

    # endregion

    def update_options(self, *args):
        old_options = dict(self.options.items())
        new_options = self.options.parse(self.window.results)
        changed = {k: v for k, v in new_options.items() if v != old_options[k]}
        if 'repl_genres' in changed or 'title_case' in changed:
            return self.set_next_view(
                old_info=self.old_info, new_info=self.new_info, options=self.options, retain_prev_view=True
            )

        self.album_diff_frame.update(self.window, changed.get('no_album_move'))  # noqa

    def _edit_album_view_spec(self) -> ViewSpec:
        from .album import AlbumView

        return AlbumView, (), {'album': self.new_info, 'editable': True, 'edited': True, 'prev_view': None}

    @button_handler('edit')
    def edit_info(self, event: Event = None, key=None) -> CallbackAction:
        view_cls, args, kwargs = self._edit_album_view_spec()
        return self.set_next_view(*args, view_cls=view_cls, **kwargs)

    def get_prev_view(self) -> ViewSpec | None:
        if self.prev_view_name == 'AlbumView':
            return self._edit_album_view_spec()
        else:
            # TODO: Remember selected wiki update options
            return super().get_prev_view()

    # region Save Changes

    @button_handler('next_view')
    def save_changes(self, event: Event = None, key=None) -> CallbackAction | None:
        from .album import AlbumView

        options = self.options.parse(self.window.results)
        dry_run = options['dry_run']
        album_dir = self.new_info.album_dir
        self._save_changes(album_dir, dry_run, options['repl_genres'], options['title_case'])
        if dry_run:
            return None

        album_dir.refresh()
        return self.set_next_view(view_cls=AlbumView, album=album_dir)

    def _save_changes(self, album_dir: AlbumDir, dry_run: bool, replace_genres: bool, title_case: bool):
        # TODO: Maybe add spinner
        image, data, mime_type = self.new_info.get_new_cover(force=True)

        file_info_map = self.new_info.get_file_info_map()
        for song_file, track_info in file_info_map.items():
            tags = track_info.tags(title_case)
            song_file.update_tags(tags, dry_run, add_genre=not replace_genres)
            if image is not None:
                song_file._set_cover_data(image, data, mime_type, dry_run)

            track_info.maybe_rename(song_file, dry_run)

        if new_album_path := self.album_diff_frame.new_album_path:  # returns None if self.options['no_album_move']
            self._move_album(album_dir, new_album_path, dry_run)

    def _move_album(self, album_dir: AlbumDir, new_album_path: Path, dry_run: bool):  # noqa
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
            if len(path.parts) > 4 and path.exists() and next(path.iterdir(), None) is None:
                log.log(19, f'Removing empty directory: {path.as_posix()}')
                try:
                    path.rmdir()
                except OSError as e:
                    popup_error(f'Unable to delete empty directory={path.as_posix()!r}:\n{e}')
                    break

    # endregion
