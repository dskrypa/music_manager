"""
View for sorting files into the final library destination, possibly moving an existing version into an archive
directory, if present.
"""

from __future__ import annotations

import logging
from shutil import rmtree
from typing import TYPE_CHECKING, Iterator

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
        for src_file, dst_file in self._iter_src_dst_files('move', logging.INFO):
            if not self.dry_run:
                src_file.rename(dst_file)

        self._rm_src_dir()

    def _same_fs_dst_missing(self):
        # Simply rename src_dir to dst_dir since they're on the same fs and dst_dir doesn't exist
        log.info(f'{self.lp.move} {path_repr(self.src_dir)} -> {path_repr(self.dst_dir)}')
        if not self.dry_run:
            self.src_dir.rename(self.dst_dir)

    def _diff_fs(self):
        # Create dst_dir if necessary, copy contents from src_dir to dst_dir, then trash/delete src_dir
        log.info(f'{self.lp.copy} {path_repr(self.src_dir)} -> {path_repr(self.dst_dir)}')
        if not self.dst_exists:
            log.debug(f'{self.lp.create} {path_repr(self.dst_dir)}')
            if not self.dry_run:
                self.dst_dir.mkdir(parents=True, exist_ok=True)

        if not self.dry_run:
            CopyFilesPopup.copy_dir(self.src_dir, self.dst_dir).run()

        if self.use_trash:
            self._trash_src_dir()
        else:
            self._rm_src_dir(True)

    def _iter_src_dst_files(self, verb: str, log_level: int) -> Iterator[tuple[Path, Path]]:
        for src_file in self.src_dir.iterdir():
            dst_file = self.dst_dir.joinpath(src_file.name)
            log.log(log_level, f'{self.lp[verb]} {path_repr(src_file)} -> {path_repr(dst_file)}')
            yield src_file, dst_file

    def _rm_src_dir(self, tree: bool = False):
        log.info(f'{self.lp.delete} {path_repr(self.src_dir)}')
        if not self.dry_run:
            if tree:
                rmtree(self.src_dir)
            else:
                self.src_dir.rmdir()

    def _trash_src_dir(self):
        log.info(f'{self.lp.send} to trash: {path_repr(self.src_dir)}')
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
