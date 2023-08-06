"""
"""

from __future__ import annotations

import logging
from datetime import date
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

from ds_tools.caching.decorators import cached_property, ClearableCachedPropertyMixin, ClearableCachedProperty
from tk_gui import popup_input_invalid, pick_folder_popup

from music.files.album import AlbumDir
from music.files.exceptions import InvalidAlbumDir

if TYPE_CHECKING:
    from tk_gui import GuiConfig, Window
    from music.manager.update import AlbumInfo
    from music.typing import OptAlbDir, OptAnyAlbum

    OptWindow = Window | None

__all__ = ['DirManager']
log = logging.getLogger(__name__)


class DirCategory(Enum):
    OUTPUT = 'output'
    LIBRARY = 'library'
    ARCHIVE = 'archive'
    SKIPPED = 'skipped'

    @classmethod
    def _missing_(cls, value):
        if isinstance(value, str):
            return cls._member_map_.get(value.upper())
        return super()._missing_(value)


class ConfigDir(ClearableCachedProperty):
    __slots__ = ('name', 'category')

    def __init__(self, category: DirCategory):
        self.category = category

    def __set_name__(self, owner, name: str):
        self.name = name
        owner._cat_dir_attr_map[self.category] = name

    def __get__(self, instance: DirManager, owner):
        if instance is None:
            return self
        elif path_str := instance.config.get(self.name):
            instance.__dict__[self.name] = path = Path(path_str).expanduser()
            return path
        else:
            return None


class DirManager(ClearableCachedPropertyMixin):
    _cat_dir_attr_map = {}

    def __init__(self, config: GuiConfig):
        self.config = config

    # region Configured Directories

    output_base_dir = ConfigDir(DirCategory.OUTPUT)
    library_base_dir = ConfigDir(DirCategory.LIBRARY)
    archive_base_dir = ConfigDir(DirCategory.ARCHIVE)
    skipped_base_dir = ConfigDir(DirCategory.SKIPPED)

    @cached_property
    def output_sorted_dir(self) -> Path:
        date_str = date.today().strftime('%Y-%m-%d')
        return self.output_base_dir.joinpath(f'sorted_{date_str}')

    def dir_for_category(self, category: DirCategory | str) -> Path:
        return getattr(self, self._cat_dir_attr_map[DirCategory(category)])

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

    def find_matching_album_dir_in_category(self, src_info: AlbumInfo, category: DirCategory | str) -> AlbumDir | None:
        return self.find_matching_album_dir(src_info, self.dir_for_category(category))

    def find_matching_album_dir(self, src_info: AlbumInfo, base_dir: Path) -> AlbumDir | None:
        for en_artist_only in (False, True):
            if dst_dir := src_info.sorter.get_new_path(base_dir, en_artist_only):
                try:
                    return AlbumDir(dst_dir)
                except InvalidAlbumDir as e:
                    log.debug(f'Unable to use {dst_dir=}: {e}')

        return None

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
