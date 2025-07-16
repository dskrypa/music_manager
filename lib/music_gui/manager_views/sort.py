"""
The "Sort Into Library" view.  Provides a way to sort files into the final library destination, possibly moving an
existing version into an archive directory, if configured.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PIL.Image import new as new_image
from send2trash import TrashPermissionError

from ds_tools.caching.decorators import cached_property
from ds_tools.fs.paths import unique_path
from tk_gui import CallbackAction, button_handler, EventButton, Text, ScrollFrame, BasicRowFrame
from tk_gui.images import Icons
from tk_gui.styles.base import DEFAULT_FONT_NAME

from music.files.album import AlbumDir
from music.manager.update import AlbumInfo
from music_gui.config import DirManager
from music_gui.elements.file_frames import SongFilesFrame
from music_gui.fs_utils import move_dir, send_to_trash
from music_gui.utils import get_album_dir, get_album_dir_and_info
from .base import BaseView

if TYPE_CHECKING:
    from pathlib import Path
    from tkinter import Event
    from tk_gui import Window, ViewSpec, Layout
    from tk_gui.typing import XY
    from music.typing import AnyAlbum

__all__ = ['AlbumSortView']
log = logging.getLogger(__name__)


class AlbumSortView(BaseView, title='Music Manager - Album Sorting'):
    default_window_kwargs = BaseView.default_window_kwargs | {'exit_on_esc': True}
    album: AlbumInfo
    src_info: AlbumInfo
    src_album: AlbumDir
    dst_album: AlbumDir | None

    def __init__(self, src_album: AnyAlbum, dst_album: AnyAlbum = None, src_info: AlbumInfo = None, **kwargs):
        super().__init__(**kwargs)
        self.src_album, self.src_info = get_album_dir_and_info(src_album, src_info)
        self.album = self.src_info
        self.dst_album = get_album_dir(dst_album) if dst_album else None

    @classmethod
    def prepare_transition(
        cls,
        dir_manager: DirManager,
        src_album: AnyAlbum = None,
        dst_album: AnyAlbum = None,
        src_info: AlbumInfo = None,
        *,
        parent: Window = None, **kwargs
    ) -> ViewSpec | None:
        if src_album or src_info:
            src_album, src_info = get_album_dir_and_info(src_album, src_info)
        elif src_album := dir_manager.select_sync_src_album(dst_album, parent, prompt='Select an album to sort'):
            src_info = AlbumInfo.from_album_dir(src_album)
        else:
            return None

        if not dst_album and src_info.type:
            dst_album = dir_manager.find_matching_album_dir_in_category(src_info, 'library')
        return cls.as_view_spec(src_album, dst_album, src_info)

    # region Layout Generation

    # def get_pre_window_layout(self) -> Layout:
    #     yield from super().get_pre_window_layout()

    @cached_property(block=False)
    def _button_icons(self) -> Icons:
        return Icons(15)

    def _make_button_icon(self, name: str, size: XY, pos: XY):
        # TODO: The process for determining the correct size/pos values to use and number of spaces to include before
        #  button text is too hit-or-miss... There must be a better (automatic) way...
        ele_style = self.window.style.button
        bg = f'{ele_style.bg.default}00'
        icon = new_image('RGBA', size, bg)
        icon.paste(self._button_icons.draw(name, color=ele_style.fg.default, bg=bg), pos)
        return icon

    def get_inner_layout(self) -> Layout:
        yield [self._prep_src_header(), self._prep_dst_header()]
        arrow = Text('\u2794', font=(DEFAULT_FONT_NAME, 20), size=(2, 1))
        # TODO: Swap src <-> dst button
        # TODO: Copy ratings button =>> diff view
        # TODO: Copy all button =>> diff view
        yield [self._prep_src_frame(), arrow, self._prep_dst_frame()]

    def _prep_src_header(self):
        # TODO: The image/text on these buttons is not displaying well at all
        trash_icon = self._make_button_icon('trash', (130, 20), (7, 3))
        album_icon = self._make_button_icon('disc', (50, 20), (0, 2))
        # Note: Spaces in text are intentional to align with icons
        view_btn = EventButton('     View', album_icon, key='view_src_album', size=(70, 20))
        trash_btn = EventButton('   Send to Trash', trash_icon, key='send_to_trash', size=(140, 20))
        skip_btn = EventButton('Move to Skipped', key='move_to_skipped_dir')
        return BasicRowFrame([view_btn, trash_btn, skip_btn], expand=True)

    def _prep_dst_header(self):
        album_icon = self._make_button_icon('disc', (50, 20), (0, 2))
        # Note: Spaces in text are intentional to align with icons
        view_btn = EventButton('     View', album_icon, key='view_dst_album', size=(70, 20))
        match_btn = EventButton('Fix Match...', key='fix_dst_match')
        replace_btn = EventButton('Replace...', key='replace_album')
        return BasicRowFrame([view_btn, match_btn, replace_btn], expand=True)

    def _prep_src_frame(self) -> ScrollFrame:
        # TODO: Source frame sometimes takes more width than necessary, and leaving not enough for the dst frame,
        #  maybe due to path length?
        return SongFilesFrame(self.src_album, border=True)

    def _prep_dst_frame(self) -> ScrollFrame:
        if self.dst_album:
            return SongFilesFrame(self.dst_album, border=True)
        else:
            # TODO: Force width to match the src side so the dst header buttons are not above the src album
            return ScrollFrame(border=True)

    # endregion

    # region Source Album Event Handlers

    @button_handler('send_to_trash')
    def send_to_trash(self, event: Event, key=None) -> CallbackAction | None:
        with SortActionWrapper(self.src_album) as wrapper:
            send_to_trash(self.src_album.path)
        return wrapper.next_view(self)

    @button_handler('move_to_skipped_dir')
    def move_to_skipped_dir(self, event: Event, key=None):
        src_path: Path = self.src_album.path
        dst_path = unique_path.for_path(self.src_info.sorter.get_new_path(self.dir_manager.skipped_base_dir))
        with SortActionWrapper(self.src_album) as wrapper:
            move_dir(src_path, dst_path)
        return wrapper.next_view(self)

    # endregion

    # region Destination Album Event Handlers

    @button_handler('view_src_album', 'view_dst_album')
    def view_album(self, event: Event, key=None) -> CallbackAction | None:
        from .album import AlbumView

        if album := self.src_album if key == 'view_src_album' else self.dst_album:
            return self.go_to_next_view(AlbumView.prepare_transition(self.dir_manager, album=album))
        return None

    @button_handler('fix_dst_match')
    def fix_dst_match(self, event: Event, key=None) -> CallbackAction | None:
        if dst_album := self._fix_dst_match():
            return self.go_to_next_view(self.as_view_spec(self.src_album, dst_album, self.src_info))
        return None

    def _fix_dst_match(self) -> AlbumDir | None:
        init_dir = find_dst_album_init_dir(self.src_info, self.dir_manager.library_base_dir)
        return self.dir_manager.select_album(init_dir, f'Select original version of {self.src_album.name}', self.window)

    @button_handler('replace_album')
    def replace_album(self, event: Event, key=None):
        # TODO: Copy ratings from dst to src
        src_path: Path = self.src_album.path
        dst_path: Path = self.dst_album.path
        arc_path = unique_path.for_path(self.src_info.sorter.get_new_path(self.dir_manager.archive_base_dir))
        with SortActionWrapper(self.src_album) as wrapper:
            move_dir(dst_path, arc_path)
            move_dir(src_path, dst_path)
        return wrapper.next_view(self)

    # endregion


class SortActionWrapper:
    __slots__ = ('next_album', '_trash_exc')

    def __init__(self, src_album: AlbumDir):
        # self.next_album = src_album.next_sibling or src_album.prev_sibling
        self.next_album = src_album.next_sibling
        self._trash_exc = None

    def next_view(self, view: AlbumSortView) -> CallbackAction | None:
        if self._trash_exc is not None:
            return None
        return view.go_to_next_view(view.prepare_transition(view.dir_manager, self.next_album), forget_last=True)

    def __enter__(self) -> SortActionWrapper:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            return True
        elif isinstance(exc_val, TrashPermissionError):  # Note: already logged / popped up by send_to_trash
            # TODO: Maybe open explorer to the containing directory?  Maybe transition anyways?
            self._trash_exc = exc_val
            return True
        else:
            return False  # Let the exception propagate


def find_dst_album_init_dir(src_info: AlbumInfo, lib_base_dir: Path) -> Path:
    album_dirs = [dst for en_only in (False, True) if (dst := src_info.sorter.get_new_path(lib_base_dir, en_only))]
    for dst_dir in album_dirs:
        if dst_dir.is_dir():
            return dst_dir

    for n in range(3):  # 0: type dir, 1: artist, 2: artists
        for dst_dir in album_dirs:
            if (path := dst_dir.parents[n]).is_dir():
                return path

    return lib_base_dir
