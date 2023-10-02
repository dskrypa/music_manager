"""

"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from pathlib import Path
from time import monotonic
from traceback import format_exc
from typing import TYPE_CHECKING, Union, Iterable, TypeVar, Iterator, Mapping

from ordered_set import OrderedSet

from ds_tools.output.prefix import LoggingPrefix
from tk_gui.elements import Element, HorizontalSeparator
from tk_gui.popups import popup_ok, popup_error
from tk_gui.styles import Style

from music.files.album import AlbumDir
from music.files.track.track import SongFile
from music.manager.update import AlbumInfo, TrackInfo

if TYPE_CHECKING:
    from tk_gui.typing import Layout

__all__ = [
    'AlbumIdentifier', 'get_album_info', 'get_album_dir', 'get_album_dir_and_info',
    'TrackIdentifier', 'get_track_info', 'get_track_file',
    'LogAndPopupHelper', 'log_and_popup_error',
    'with_separators', 'fix_windows_path', 'call_timer', 'zip_maps', 'find_value', 'find_values',
]
log = logging.getLogger(__name__)

_NotSet = object()
AlbumIdentifier = Union[AlbumInfo, AlbumDir, Path, str]
TrackIdentifier = Union[TrackInfo, SongFile, Path, str]
K = TypeVar('K')
V = TypeVar('V')
D = TypeVar('D')


# region Log + Popup Helpers


class LogAndPopupHelper:
    __slots__ = ('popup_title', 'dry_run', 'lp', 'messages', 'log_level', 'default_message')

    def __init__(self, popup_title: str, dry_run: bool, default_message: str = None, log_level: int = logging.INFO):
        self.popup_title = popup_title
        self.dry_run = dry_run
        self.lp = LoggingPrefix(dry_run)
        self.messages = []
        self.log_level = log_level
        self.default_message = default_message

    def write(self, prefix: str, message: str):
        with self.lp.past_tense() as lp:
            self.messages.append(f'{lp[prefix]} {message}')
        # The below message ends up using present tense
        log.log(self.log_level, f'{lp[prefix]} {message}')

    def __enter__(self) -> LogAndPopupHelper:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_val is not None:
            return
        if message := '\n\n'.join(self.messages) or self.default_message:
            popup_ok(message, title=self.popup_title)

    def took_action(self, ignore_dry_run: bool = False) -> bool:
        if self.dry_run and not ignore_dry_run:
            return False
        return bool(self.messages)


def log_and_popup_error(message: str, exc_info: bool = False):
    kwargs = {'multiline': True}
    if exc_info:
        message += '\n' + format_exc()
        kwargs['text_kwargs'] = {'style': Style.default_style.sub_style(text_font=('Consolas', 11))}

    log.error(message)
    popup_error(message, **kwargs)


# endregion


# region Album / Track Type Normalization


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


def get_album_dir_and_info(*album_identifiers: AlbumIdentifier) -> tuple[AlbumDir, AlbumInfo]:
    if not album_identifiers:
        raise ValueError('At least one album identifier is required')

    album_dir = album_info = None
    for ai in album_identifiers:
        if isinstance(ai, AlbumInfo):
            album_info = ai
        elif isinstance(ai, AlbumDir):
            album_dir = ai
        elif isinstance(ai, (Path, str)):
            album_dir = AlbumDir(_album_directory(ai))

    if album_info is None:
        if album_dir is None:
            raise ValueError(f'None of the provided {album_identifiers=} were valid')
        album_info = AlbumInfo.from_album_dir(album_dir)
    elif album_dir is None:
        album_dir = album_info.album_dir

    return album_dir, album_info


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


# endregion


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


def zip_maps(*mappings: Mapping[K, V]) -> Iterator[tuple[K, V, ...]]:
    keys = OrderedSet(mappings[0]).intersection(*mappings[1:])
    for key in keys:
        yield key, *(m[key] for m in mappings)


def find_value(key: K, *mappings: Mapping[K, V], default: D = _NotSet) -> V | D:
    for mapping in mappings:
        try:
            return mapping[key]
        except KeyError:
            pass
    if default is _NotSet:
        raise KeyError(key)
    return default


def find_values(keys: Iterable[K], *mappings: Mapping[K, V], default: D = _NotSet) -> dict[K, V | D]:
    results = {}
    for key in keys:
        try:
            results[key] = find_value(key, *mappings, default=default)
        except KeyError:
            pass
    return results
