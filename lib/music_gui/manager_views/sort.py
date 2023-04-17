"""
View for sorting files into the final library destination, possibly moving an existing version into an archive
directory, if present.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PIL.Image import new as new_image
from tk_gui import CallbackAction, button_handler, EventButton, Text, ScrollFrame, BasicRowFrame
from tk_gui.images import Icons

from music.files.album import AlbumDir, InvalidAlbumDir
from music.manager.update import AlbumInfo
from music_gui.elements.file_frames import SongFilesFrame
from music_gui.utils import get_album_info, get_album_dir
from .base import BaseView, DirManager

if TYPE_CHECKING:
    from pathlib import Path
    from tkinter import Event
    from tk_gui import Window, ViewSpec, Layout
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
        self.album = self.src_info = src_info if src_info else get_album_info(src_album)
        self.src_album = get_album_dir(src_album)
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
        if not src_album and not (src_album := dir_manager.select_sync_src_album(dst_album, parent)):
            return None
        if not dst_album and src_album.type:
            dst_album = find_dst_album_dir(src_album, dir_manager.library_base_dir)
        return cls.as_view_spec(src_album, dst_album, src_info)

    # region Layout Generation

    # def get_pre_window_layout(self) -> Layout:
    #     yield from super().get_pre_window_layout()

    def get_inner_layout(self) -> Layout:
        yield [self._prep_src_header(), self._prep_dst_header()]
        arrow = Text('\u2794', font=('Helvetica', 20), size=(2, 1))
        yield [self._prep_src_frame(), arrow, self._prep_dst_frame()]

    def _prep_src_header(self):
        ele_style = self.window.style.button
        bg = f'{ele_style.bg.default}00'
        trash_icon = new_image('RGBA', (130, 20), bg)
        trash_icon.paste(Icons(15).draw('trash', color=ele_style.fg.default, bg=bg), (7, 3))
        # Note: Spaces in text are intentional to align with the icon
        trash_btn = EventButton('   Send to Trash', trash_icon, key='send_to_trash', size=(140, 20))
        skip_btn = EventButton('Move to Skipped', key='move_to_skipped_dir')
        return BasicRowFrame([trash_btn, skip_btn], expand=True)

    def _prep_dst_header(self):
        match_btn = EventButton('Fix Match...', key='fix_dst_match')
        replace_btn = EventButton('Replace...', key='replace_album')
        return BasicRowFrame([match_btn, replace_btn], expand=True)

    def _prep_src_frame(self) -> ScrollFrame:
        return SongFilesFrame(self.src_album, border=True)

    def _prep_dst_frame(self) -> ScrollFrame:
        if self.dst_album:
            return SongFilesFrame(self.dst_album, border=True)
        else:
            return ScrollFrame(border=True)

    # endregion

    # region Source Album Event Handlers

    @button_handler('send_to_trash')
    def send_to_trash(self, event: Event, key=None):
        pass

    @button_handler('move_to_skipped_dir')
    def move_to_skipped_dir(self, event: Event, key=None):
        pass

    # endregion

    # region Destination Album Event Handlers

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
        pass

    # endregion


def find_dst_album_dir(src_album: AlbumInfo, lib_base_dir: Path) -> AlbumDir | None:
    for en_artist_only in (False, True):
        if dst_dir := src_album.sorter.get_new_path(lib_base_dir, en_artist_only):
            try:
                return AlbumDir(dst_dir)
            except InvalidAlbumDir as e:
                log.debug(f'Unable to use {dst_dir=}: {e}')

    return None


def find_dst_album_init_dir(src_album: AlbumInfo, lib_base_dir: Path) -> Path:
    album_dirs = [dst for en_only in (False, True) if (dst := src_album.sorter.get_new_path(lib_base_dir, en_only))]
    for dst_dir in album_dirs:
        if dst_dir.is_dir():
            return dst_dir

    for n in range(3):  # 0: type dir, 1: artist, 2: artists
        for dst_dir in album_dirs:
            if (path := dst_dir.parents[n]).is_dir():
                return path

    return lib_base_dir