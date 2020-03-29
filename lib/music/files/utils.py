"""
:author: Doug Skrypa
"""

import logging
from typing import Iterator, Iterable, Union

from ds_tools.core.filesystem import iter_files, Paths
from .track.track import SongFile

__all__ = ['iter_music_files', 'sanitize_path', 'SafePath']
log = logging.getLogger(__name__)

NON_MUSIC_EXTS = {'jpg', 'jpeg', 'png', 'jfif', 'part', 'pdf', 'zip', 'webp'}
PATH_SANITIZATION_DICT = {c: '' for c in '*;?<>"'}
PATH_SANITIZATION_DICT.update({'/': '_', ':': '-', '\\': '_', '|': '-'})
PATH_SANITIZATION_TABLE = str.maketrans(PATH_SANITIZATION_DICT)


def iter_music_files(paths: Paths) -> Iterator[SongFile]:
    for file_path in iter_files(paths):
        music_file = SongFile(file_path)
        if music_file:
            yield music_file
        else:
            if file_path.suffix not in NON_MUSIC_EXTS:
                log.debug('Not a music file: {}'.format(file_path))


def sanitize_path(text: str) -> str:
    return text.translate(PATH_SANITIZATION_TABLE)


class SafePath:
    def __init__(self, parts: Union[str, Iterable[str]]):
        if isinstance(parts, str):
            self.parts = parts.split('/')
        else:
            self.parts = parts

    def __call__(self, **kwargs) -> str:
        return '/'.join(sanitize_path(part.format(**kwargs)) for part in self.parts)

    def __repr__(self):
        return f'<{self.__class__.__name__}({"/".join(self.parts)!r})>'
