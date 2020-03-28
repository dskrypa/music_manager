"""
:author: Doug Skrypa
"""

import logging
import string
from typing import Iterator
from unicodedata import normalize

from ds_tools.core.filesystem import iter_files, Paths
from .track.track import SongFile

__all__ = ['iter_music_files', 'tag_repr']
log = logging.getLogger(__name__)

NON_MUSIC_EXTS = {'jpg', 'jpeg', 'png', 'jfif', 'part', 'pdf', 'zip', 'webp'}
# Translate whitespace characters (such as \n, \r, etc.) to their escape sequences
WHITESPACE_TRANS_TBL = str.maketrans({c: c.encode('unicode_escape').decode('utf-8') for c in string.whitespace})


def tag_repr(tag_val, max_len=125, sub_len=25):
    tag_val = normalize('NFC', str(tag_val)).translate(WHITESPACE_TRANS_TBL)
    if len(tag_val) > max_len:
        return '{}...{}'.format(tag_val[:sub_len], tag_val[-sub_len:])
    return tag_val


def iter_music_files(paths: Paths) -> Iterator[SongFile]:
    for file_path in iter_files(paths):
        music_file = SongFile(file_path)
        if music_file:
            yield music_file
        else:
            if file_path.suffix not in NON_MUSIC_EXTS:
                log.debug('Not a music file: {}'.format(file_path))
