"""
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from ds_tools.caching.decorators import cached_property, ClearableCachedPropertyMixin, ClearableCachedProperty
from tk_gui import popup_input_invalid, pick_folder_popup

from music.files.album import AlbumDir
from music.files.exceptions import InvalidAlbumDir

if TYPE_CHECKING:
    from tk_gui import GuiConfig, Window
    from music.typing import OptAlbDir, OptAnyAlbum

    OptWindow = Window | None

__all__ = ['DirManager']
log = logging.getLogger(__name__)


class ConfigDir(ClearableCachedProperty):
    __slots__ = ('name',)

    def __set_name__(self, owner, name: str):
        self.name = name

    def __get__(self, instance: DirManager, owner):
        if instance is None:
            return self
        elif path_str := instance.config.get(self.name):
            instance.__dict__[self.name] = path = Path(path_str).expanduser()
            return path
        else:
            return None


class DirManager(ClearableCachedPropertyMixin):
    def __init__(self, config: GuiConfig):
        self.config = config

    # region Configured Directories

    output_base_dir = ConfigDir()
    library_base_dir = ConfigDir()
    archive_base_dir = ConfigDir()
    skipped_base_dir = ConfigDir()

    @cached_property
    def output_sorted_dir(self) -> Path:
        date_str = date.today().strftime('%Y-%m-%d')
        return self.output_base_dir.joinpath(f'sorted_{date_str}')

    # endregion

    def get_any_dir_selection(self, prompt: str = None, dir_type: str = None, parent: Window = None) -> Path | None:
        last_dir = self._get_last_dir(dir_type)
        if path := pick_folder_popup(last_dir, prompt or 'Pick Directory', parent=parent):
            log.debug(f'Selected directory {path=}')
            if path != last_dir:
                self._set_last_dir(path, dir_type)
        return path

    def get_album_selection(self, prompt: str = None, dir_type: str = None, parent: Window = None) -> OptAlbDir:
        last_dir = self._get_last_dir(dir_type)
        if (album_dir := self.select_album(last_dir, prompt, parent)) and album_dir.path != last_dir:
            self._set_last_dir(album_dir.path, dir_type)
        return album_dir

    def select_album(self, last_dir: Path | None, prompt: str = None, parent: Window = None) -> OptAlbDir:  # noqa
        if path := pick_folder_popup(last_dir, prompt or 'Pick Album Directory', parent=parent):
            log.debug(f'Selected album {path=}')
            try:
                return AlbumDir(path)
            except InvalidAlbumDir as e:
                popup_input_invalid(str(e), logger=log)
        return None

    def _get_last_dir(self, dir_type: str = None) -> Path | None:
        key = f'last_dir:{dir_type}' if dir_type else 'last_dir'
        if last_dir := self.config.get(key):
            last_dir = Path(last_dir)
            if last_dir.exists():
                return last_dir
            elif last_dir.parent.exists():
                return last_dir.parent
            else:
                return self.output_base_dir
        return None

    def _set_last_dir(self, path: Path, dir_type: str = None):
        key = f'last_dir:{dir_type}' if dir_type else 'last_dir'
        self.config[key] = path.as_posix()
        self.config.save()

    # region Select Sync Album

    def select_sync_src_album(self, dst_album: OptAnyAlbum, parent: OptWindow = None, prompt: str = None) -> OptAlbDir:
        return self.select_sync_album(dst_album, 'sync_src', parent, prompt)

    def select_sync_dst_album(self, src_album: OptAnyAlbum, parent: OptWindow = None, prompt: str = None) -> OptAlbDir:
        return self.select_sync_album(src_album, 'sync_dst', parent, prompt)

    def select_sync_album(self, other: OptAnyAlbum, dir_type: str, parent: OptWindow, prompt: str = None) -> OptAlbDir:
        ver = 'original' if dir_type == 'sync_src' else 'new'
        if not prompt:
            prompt = f'Select {ver} version of {other.name}' if other else None
        return self.get_album_selection(prompt, dir_type, parent)

    # endregion
