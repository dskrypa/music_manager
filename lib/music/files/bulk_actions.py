"""

"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TYPE_CHECKING, Iterator

if TYPE_CHECKING:
    from music.typing import Strings
    from .album import AlbumDir
    from .track.track import SongFile
    from .typing import ProgressCB, TrackIter

__all__ = ['remove_bad_tags', 'fix_song_tags']
log = logging.getLogger(__name__)


def remove_bad_tags(tracks: TrackIter, dry_run: bool = False, cb: ProgressCB = None, extras: Strings = None):
    from .album import AlbumDir

    if not sum(music_file.remove_bad_tags(dry_run, extras) for music_file in _iter_with_callbacks(tracks, cb)):
        mid = f'songs in {tracks}' if isinstance(tracks, AlbumDir) else 'provided songs'
        log.debug(f'None of the {mid} had any tags that needed to be removed')


def fix_song_tags(tracks: TrackIter, dry_run: bool = False, add_bpm: bool = False, cb: ProgressCB = None):
    for music_file in _iter_with_callbacks(tracks, cb):
        music_file.fix_song_tags(dry_run)

    if not add_bpm:
        return

    with ThreadPoolExecutor(max_workers=8) as executor:
        for future in as_completed([executor.submit(f.maybe_add_bpm, dry_run) for f in tracks if f is not None]):
            future.result()


def _iter_with_callbacks(tracks: TrackIter, callback: ProgressCB = None) -> Iterator[SongFile]:
    for n, music_file in enumerate(tracks, 1):
        if callback:
            callback(music_file, n)

        yield music_file
