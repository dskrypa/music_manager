"""
:author: Doug Skrypa
"""

import logging
from itertools import chain
from typing import TYPE_CHECKING, Iterator, Iterable, Union, Mapping, Any, Dict, Tuple

from ds_tools.fs.paths import iter_files, Paths
from .track import SongFile, print_tag_changes, count_tag_changes

if TYPE_CHECKING:
    from .album import AlbumDir

__all__ = ['iter_music_files', 'sanitize_path', 'SafePath', 'get_common_changes']
log = logging.getLogger(__name__)


def iter_music_files(paths: Paths) -> Iterator[SongFile]:
    non_music_exts = {'jpg', 'jpeg', 'png', 'jfif', 'part', 'pdf', 'zip', 'webp'}
    for file_path in iter_files(paths):
        music_file = SongFile(file_path)
        if music_file:
            yield music_file
        else:
            if file_path.suffix not in non_music_exts:
                log.log(5, 'Not a music file: {}'.format(file_path))


def sanitize_path(text: str) -> str:
    try:
        table = sanitize_path._table
    except AttributeError:
        path_sanitization_dict = {c: '' for c in '*;?<>"'}
        path_sanitization_dict.update({'/': '_', ':': '-', '\\': '_', '|': '-'})
        table = sanitize_path._table = str.maketrans(path_sanitization_dict)
    return text.translate(table)


class SafePath:
    def __init__(self, parts: Union[str, Iterable[str]]):
        if isinstance(parts, str):
            self.parts = parts.split('/')
        else:
            self.parts = parts

    def __call__(self, **kwargs) -> str:
        # log.debug('Generating safe path for: {}'.format(json.dumps(kwargs, sort_keys=True, indent=4)))
        return '/'.join(sanitize_path(part.format(**kwargs)) for part in self.parts)

    def __repr__(self):
        return f'<{self.__class__.__name__}({"/".join(self.parts)!r})>'

    def __add__(self, other: 'SafePath') -> 'SafePath':
        return SafePath(tuple(chain(self.parts, other.parts)))

    def __iadd__(self, other: 'SafePath') -> 'SafePath':
        self.parts = tuple(chain(self.parts, other.parts))
        return self


def get_common_changes(
    album_dir: 'AlbumDir', updates: Mapping['SongFile', Mapping[str, Any]], show=True, extra_newline=False,
    dry_run=False
) -> Dict[str, Tuple[Any, Any]]:
    counts = count_tag_changes(updates)
    # noinspection PyUnboundLocalVariable
    common_changes = {
        tag_name: val_tup for tag_name, tag_counts in sorted(counts.items())
        if len(tag_counts) == 1 and (val_tup := next(iter(tag_counts))) and val_tup[0] != val_tup[1]
    }
    if show and common_changes:
        if extra_newline:
            print()
        print_tag_changes(album_dir, common_changes, dry_run, 10)
        print()

    return common_changes
