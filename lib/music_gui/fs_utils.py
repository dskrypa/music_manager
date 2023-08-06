"""
View for sorting files into the final library destination, possibly moving an existing version into an archive
directory, if present.
"""

from __future__ import annotations

import logging
from shutil import rmtree
from typing import TYPE_CHECKING

from send2trash import send2trash, TrashPermissionError

from ds_tools.fs.mount_info import on_same_fs
from ds_tools.fs.paths import path_repr
from ds_tools.output.prefix import LoggingPrefix
from tk_gui.popups.files import CopyFilesPopup

from music_gui.utils import log_and_popup_error

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ['move_dir', 'send_to_trash']
log = logging.getLogger(__name__)


def move_dir(src_dir: Path, dst_dir: Path, *, use_trash: bool = True, dry_run: bool = False):
    return DirMover(src_dir, dst_dir, use_trash=use_trash, dry_run=dry_run).move()


class DirMover:
    __slots__ = ('src_dir', 'dst_dir', 'lp', 'dry_run', 'use_trash', 'dst_exists')

    def __init__(self, src_dir: Path, dst_dir: Path, *, use_trash: bool = True, dry_run: bool = False):
        if (dst_exists := dst_dir.exists()) and not dst_dir.is_dir():
            raise FileExistsError(f'dst_dir={path_repr(dst_dir)} already exists, but it is not a directory')
        self.src_dir = src_dir
        self.dst_dir = dst_dir
        self.dry_run = dry_run
        self.use_trash = use_trash
        self.dst_exists = dst_exists
        self.lp = LoggingPrefix(dry_run)

    def move(self):
        if on_same_fs(self.src_dir, self.dst_dir):
            if self.dst_exists:
                self._same_fs_dst_exists()
            else:
                self._same_fs_dst_missing()
        else:
            self._diff_fs()

    def _same_fs_dst_exists(self):
        # Rename files individually since dst_dir already exists, then delete src_dir
        dst_join = self.dst_dir.joinpath
        src_dst_paths = [(src_path, dst_join(src_path.name)) for src_path in self.src_dir.iterdir()]
        if dst_exists := [dst_path.as_posix() for _, dst_path in src_dst_paths if dst_path.exists()]:
            if len(dst_exists) == len(src_dst_paths):
                msg = 'all destination paths already exist'
            else:
                msg = f'{len(dst_exists)} path(s) already exist: ' + ', '.join(map(repr, sorted(dst_exists)))

            raise FileExistsError(
                f'Unable to copy src={self.src_dir.as_posix()} to dst={self.dst_dir.as_posix()} - {msg}'
            )

        for src_path, dst_path in src_dst_paths:
            log.info(f'{self.lp.move} {path_repr(src_path)} -> {path_repr(dst_path)}')
            if not self.dry_run:
                src_path.rename(dst_path)  # Will raise FileExistsError if dst_file already exists

        self._rm_src_dir()

    def _maybe_mkdir(self, path: Path, exists: bool = None):
        if exists is None:
            exists = path.exists()
        if not exists:
            log.debug(f'{self.lp.create} {path_repr(path)}')
            if not self.dry_run:
                path.mkdir(parents=True, exist_ok=True)

    def _same_fs_dst_missing(self):
        # Simply rename src_dir to dst_dir since they're on the same fs and dst_dir doesn't exist
        self._maybe_mkdir(self.dst_dir.parent)
        log.info(f'{self.lp.move} {path_repr(self.src_dir)} -> {path_repr(self.dst_dir)}')
        if not self.dry_run:
            self.src_dir.rename(self.dst_dir)

    def _diff_fs(self):
        # Create dst_dir if necessary, copy contents from src_dir to dst_dir, then trash/delete src_dir
        log.info(f'{self.lp.copy} {path_repr(self.src_dir)} -> {path_repr(self.dst_dir)}')
        self._maybe_mkdir(self.dst_dir, self.dst_exists)
        if not self.dry_run:
            CopyFilesPopup.copy_dir(self.src_dir, self.dst_dir).run()

        if self.use_trash:
            self._trash_src_dir()
        else:
            self._rm_src_dir(True)

    def _rm_src_dir(self, tree: bool = False):
        log.info(f'{self.lp.delete} {path_repr(self.src_dir)}', extra={'color': 'red'})
        if not self.dry_run:
            if tree:
                rmtree(self.src_dir)
            else:
                self.src_dir.rmdir()

    def _trash_src_dir(self):
        log.info(f'{self.lp.send} to trash: {path_repr(self.src_dir)}', extra={'color': 'red'})
        if not self.dry_run:
            send_to_trash(self.src_dir)


def send_to_trash(path: Path):
    try:
        send2trash(path)
    except TrashPermissionError as e:
        # Likely causes include the file being on a network fs, or, on Windows, the directory (or a file in it)
        # is "open" in another program (such as a terminal window opened with that dir as its initial dir).
        log_and_popup_error(f'Unable to send {path.as_posix()} to trash: {e}')
        raise
