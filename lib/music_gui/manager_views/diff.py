"""
View that provides a diff between original Album/track info and submitted/proposed changes.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Mapping, Any

from ds_tools.caching.decorators import cached_property
from ds_tools.output.prefix import LoggingPrefix
from tk_gui import CallbackAction, button_handler, popup_error
from tk_gui.options import GuiOptions, BoolOption

from music.files.album import AlbumDir
from music.manager.update import AlbumInfo
from music_gui.elements.diff_frames import AlbumDiffFrame
from music_gui.elements.helpers import nav_button
from music_gui.utils import get_album_info
from .base import BaseView, DirManager

if TYPE_CHECKING:
    from tkinter import Event
    from tk_gui import Button, Window, ViewSpec, Layout
    from music.typing import AnyAlbum

__all__ = ['AlbumDiffView', 'FullSyncDiffView']
log = logging.getLogger(__name__)


class AlbumDiffView(BaseView, title='Music Manager - Album Info Diff'):
    default_window_kwargs = BaseView.default_window_kwargs | {'exit_on_esc': True}
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
        self.state_data['modified'] = True

    @classmethod
    def prepare_transition(cls, dir_manager: DirManager, **kwargs) -> ViewSpec | None:
        return None

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
        return self.init_gui_options([options], self._options)

    @cached_property
    def album_diff_frame(self) -> AlbumDiffFrame:
        return AlbumDiffFrame(
            self.old_info,
            self.new_info,
            output_sorted_dir=self.dir_manager.output_sorted_dir,
            options=self.options,
            update_options_cb=self.update_options,
            show_edit=self.gui_state.prev_view_name == 'WikiUpdateView',
        )

    @cached_property
    def back_button(self) -> Button | None:
        if (prev_view_name := self.gui_state.prev_view_name) == 'WikiUpdateView':
            tooltip = 'Return to wiki match options'
        elif prev_view_name == 'AlbumView':
            tooltip = 'Edit album'
        else:
            tooltip = None
        return nav_button('left', tooltip=tooltip)

    @cached_property
    def next_button(self) -> Button | None:
        # Note: Sometimes clicking this button doesn't seem to register on the 1st (or even 2nd) time
        # The problem seems to be related to tooltips: https://github.com/python/cpython/issues/90338
        return nav_button('right', tooltip='Save Changes')

    def get_inner_layout(self) -> Layout:
        yield [self.album_diff_frame]

    # endregion

    def update_options(self, *args):
        old_options = dict(self.options.items())
        new_options = self.options.parse(self.window.results)
        changed = {k: v for k, v in new_options.items() if v != old_options[k]}
        self.update_gui_options(new_options)
        if 'repl_genres' in changed or 'title_case' in changed:
            # TODO: Only refresh on these if it will actually change something
            spec = self.as_view_spec(old_info=self.old_info, new_info=self.new_info, options=self.options)
            return self.go_to_next_view(spec, forget_last=True)

        self.album_diff_frame.update(self.window)  # noqa

    def _edit_album_view_kwargs(self) -> dict[str, Any]:
        return {'album': self.new_info, 'editable': True, 'edited': True}

    @button_handler('edit')
    def edit_info(self, event: Event = None, key=None) -> CallbackAction:
        from .album import AlbumView

        self.gui_state.clear_history()
        return self.go_to_next_view(AlbumView.as_view_spec(**self._edit_album_view_kwargs()), forget_last=True)

    def go_to_prev_view(self, **kwargs) -> CallbackAction | None:
        if self.gui_state.prev_view_name == 'AlbumView':
            kwargs.update(forget_last=True, **self._edit_album_view_kwargs())
        return super().go_to_prev_view(**kwargs)

    # region Save Changes

    @button_handler('next_view')
    def save_changes(self, event: Event = None, key=None) -> CallbackAction | None:
        from .album import AlbumView

        options = self.options.parse(self.window.results)
        self.update_gui_options(options)
        dry_run = options['dry_run']
        album_dir = self.new_info.album_dir
        self._save_changes(album_dir, dry_run, options['repl_genres'], options['title_case'])
        if dry_run:
            return None

        album_dir.refresh()
        return self.go_to_next_view(AlbumView.as_view_spec(album_dir))

    def _save_changes(self, album_dir: AlbumDir, dry_run: bool, replace_genres: bool, title_case: bool):
        image, data, mime_type = self.new_info.get_new_cover(force=True)

        file_info_map = self.new_info.get_file_info_map()
        for song_file, track_info in file_info_map.items():
            tags = track_info.tags(title_case)
            song_file.update_tags(tags, dry_run, add_genre=not replace_genres)
            if image is not None:
                song_file.set_prepared_cover_data(image, data, mime_type, dry_run)

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


class FullSyncDiffView(AlbumDiffView):
    @classmethod
    def prepare_transition(
        cls,
        dir_manager: DirManager,
        src_album: AnyAlbum = None,
        dst_album: AnyAlbum = None,
        *,
        parent: Window = None, **kwargs
    ) -> ViewSpec | None:
        if not src_album and not (src_album := dir_manager.select_sync_src_album(dst_album, parent)):
            return None
        if not dst_album and not (dst_album := dir_manager.select_sync_dst_album(src_album, parent)):
            return None

        old_info = get_album_info(dst_album)
        new_info = old_info | get_album_info(src_album)
        return cls.as_view_spec(old_info, new_info, manually_edited=new_info.type is None)
