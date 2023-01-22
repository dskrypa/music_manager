"""

"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from pathlib import Path
from time import monotonic
from typing import TYPE_CHECKING, Union, Iterable

from tk_gui.elements import Element, HorizontalSeparator

from music.files.album import AlbumDir
from music.files.track.track import SongFile
from music.manager.update import AlbumInfo, TrackInfo

if TYPE_CHECKING:
    from tk_gui.typing import Layout

__all__ = [
    'AlbumIdentifier', 'get_album_info', 'get_album_dir',
    'TrackIdentifier', 'get_track_info', 'get_track_file',
    'with_separators', 'fix_windows_path', 'call_timer',
]
log = logging.getLogger(__name__)

AlbumIdentifier = Union[AlbumInfo, AlbumDir, Path, str]
TrackIdentifier = Union[TrackInfo, SongFile, Path, str]


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


def get_track_info(track: TrackIdentifier) -> TrackInfo:
    if isinstance(track, (Path, str)):
        track = SongFile(track)
    if isinstance(track, SongFile):
        track = TrackInfo.from_file(track)
    return track


def get_track_file(track: TrackIdentifier) -> SongFile:
    if isinstance(track, TrackInfo):
        track = track.path
    if isinstance(track, (str, Path)):
        track = SongFile(track)
    return track


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


@contextmanager
def call_timer(message: str):
    start = monotonic()
    yield
    elapsed = monotonic() - start
    log.debug(f'{message} in seconds={elapsed:,.3f}')
