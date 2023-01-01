"""

"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Union, Iterable

from tk_gui.elements import Element, HorizontalSeparator

from music.files.album import AlbumDir
from music.manager.update import AlbumInfo

if TYPE_CHECKING:
    from tk_gui.typing import Layout

__all__ = ['AlbumIdentifier', 'get_album_info', 'get_album_dir', 'with_separators', 'fix_windows_path']
log = logging.getLogger(__name__)

AlbumIdentifier = Union[AlbumInfo, AlbumDir, Path, str]


def get_album_info(album: AlbumIdentifier) -> AlbumInfo:
    if isinstance(album, AlbumDir):
        album = AlbumInfo.from_album_dir(album)
    elif isinstance(album, (Path, str)):
        album = AlbumInfo.from_path(_album_directory(album))
    return album


def get_album_dir(album: AlbumIdentifier) -> AlbumDir:
    if isinstance(album, AlbumInfo):
        album = album.album_dir
    elif isinstance(album, (Path, str)):
        album = AlbumDir(_album_directory(album))
    return album


def _album_directory(path: Path | str) -> Path:
    path = fix_windows_path(Path(path).expanduser())
    if not path.is_dir():
        return path.parent
    return path


def with_separators(rows: Iterable[Element | Iterable[Element]], wrap: bool = False) -> Layout:
    for i, row in enumerate(rows):
        if i:
            yield [HorizontalSeparator()]
        yield [row] if wrap else row


def fix_windows_path(path: Path) -> Path:
    """
    Fix Windows paths that were auto-completed by git bash to begin with ``/{drive}/...`` instead of ``{drive}:/...``.
    """
    if os.name != 'nt' or path.exists() or not path.as_posix().startswith('/'):
        return path

    try:
        _, drive_letter, *parts = path.parts
    except ValueError:
        return path

    if len(drive_letter) != 1:
        return path

    drive = drive_letter.upper() + ':/'
    alt_path = Path(drive, *parts)
    if alt_path.exists() or (Path(drive).exists() and not Path(f'/{drive_letter}/').exists()):
        return alt_path
    else:
        return path
