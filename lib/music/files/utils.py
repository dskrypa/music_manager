"""
:author: Doug Skrypa
"""

import logging
from typing import Iterator

from ds_tools.core.filesystem import iter_files, Paths
from .track.track import SongFile

__all__ = ['iter_music_files']
log = logging.getLogger(__name__)

NON_MUSIC_EXTS = {'jpg', 'jpeg', 'png', 'jfif', 'part', 'pdf', 'zip', 'webp'}


def iter_music_files(paths: Paths) -> Iterator[SongFile]:
    for file_path in iter_files(paths):
        music_file = SongFile(file_path)
        if music_file:
            yield music_file
        else:
            if file_path.suffix not in NON_MUSIC_EXTS:
                log.debug('Not a music file: {}'.format(file_path))
