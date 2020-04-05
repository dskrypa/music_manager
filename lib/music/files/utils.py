"""
:author: Doug Skrypa
"""

import logging
import re
from itertools import chain
from typing import Iterator, Iterable, Union, List, Tuple, Optional

from ds_tools.core.filesystem import iter_files, Paths
from ..text import Name, split_enclosed
from .track.track import SongFile

__all__ = ['iter_music_files', 'sanitize_path', 'SafePath', 'split_artists']
log = logging.getLogger(__name__)

NON_MUSIC_EXTS = {'jpg', 'jpeg', 'png', 'jfif', 'part', 'pdf', 'zip', 'webp'}
PATH_SANITIZATION_DICT = {c: '' for c in '*;?<>"'}
PATH_SANITIZATION_DICT.update({'/': '_', ':': '-', '\\': '_', '|': '-'})
PATH_SANITIZATION_TABLE = str.maketrans(PATH_SANITIZATION_DICT)
DELIMS_PAT = re.compile('(?:[;,&]| [x×] )', re.IGNORECASE)
CONTAINS_DELIM = DELIMS_PAT.search
SPLIT_STR_LIST = DELIMS_PAT.split
UNZIPPED_LIST_MATCH = re.compile(r'([;,&]| [x×] ).*?[(\[].*?\1', re.IGNORECASE).search


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

    def __add__(self, other: 'SafePath') -> 'SafePath':
        return SafePath(tuple(chain(self.parts, other.parts)))

    def __iadd__(self, other: 'SafePath') -> 'SafePath':
        self.parts = tuple(chain(self.parts, other.parts))
        return self


def split_str_list(text: str):
    return map(str.strip, SPLIT_STR_LIST(text))


def split_artists(text: str) -> List[Name]:
    artists = []
    if parts := _unzipped_parts(text):
        log.debug(f'Split {parts=}')
        for pair in zip(*map(split_str_list, parts)):
            log.debug(f'Found {pair=!r}')
            artists.append(Name.from_parts(pair))
    else:
        for part in split_str_list(text):
            log.debug(f'Found {part=!r}')
            parts = split_enclosed(text, True, maxsplit=1)
            if len(parts) == 2 and CONTAINS_DELIM(parts[1]):
                log.debug(f'Split group/members {parts=}')
                name = Name.from_enclosed(parts[0])
                name.extra = {'members': split_artists(parts[1])}
            elif len(parts) == 2 and parts[1].startswith('from '):
                log.debug(f'Split soloist/group {parts=}')
                name = Name.from_enclosed(parts[0])
                name.extra = {'group': Name.from_enclosed(parts[1])}
            else:
                log.debug(f'No custom action for {parts=}')
                name = Name.from_enclosed(part)
            artists.append(name)

    return artists


def _unzipped_parts(text: str) -> Optional[Tuple[str, str]]:
    if UNZIPPED_LIST_MATCH(text):
        parts = split_enclosed(text, True, maxsplit=1)
        if parts[0].count(',') == parts[1].count(','):
            # noinspection PyTypeChecker
            return parts
    return None
