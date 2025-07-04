"""
:author: Doug Skrypa
"""

from __future__ import annotations

import re
from itertools import chain
from abc import ABC, abstractmethod
from functools import cached_property
from pathlib import Path
from platform import system
from typing import TYPE_CHECKING, Iterable, Union

if TYPE_CHECKING:
    from plexapi.audio import Track
    from ..typing import PathLike

__all__ = ['FileBasedObject', 'SafePath', 'sanitize_path', 'plex_track_path']

ON_WINDOWS = system().lower() == 'windows'


class SafePath:
    __slots__ = ('parts',)

    def __init__(self, parts: Union[str, Iterable[str]]):
        if isinstance(parts, str):
            self.parts = parts.split('/')
        else:
            self.parts = parts

    def __call__(self, **kwargs) -> str:
        # print('Generating safe path for: {}'.format(json.dumps(kwargs, sort_keys=True, indent=4)))
        return '/'.join(sanitize_path(part.format(**kwargs)) for part in self.parts)

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__}({"/".join(self.parts)!r})>'

    def __add__(self, other: SafePath) -> SafePath:
        return SafePath(tuple(chain(self.parts, other.parts)))

    def __iadd__(self, other: SafePath) -> SafePath:
        self.parts = tuple(chain(self.parts, other.parts))
        return self


class FileBasedObject(ABC):
    @property
    @abstractmethod
    def path(self) -> Path:
        raise NotImplementedError

    @property
    def rel_path(self) -> str:
        try:
            return self.path.relative_to(Path.cwd()).as_posix()
        except Exception:  # noqa
            return self.path.as_posix()

    def basename(self, no_ext: bool = False, trim_prefix: bool = False) -> str:
        basename = self.path.stem if no_ext else self.path.name
        return _trim_prefix(basename) if trim_prefix else basename

    @cached_property
    def ext(self) -> str:
        return self.path.suffix[1:]

    def __fspath__(self) -> str:
        return self.path.as_posix()


def sanitize_path(text: str) -> str:
    try:
        table = sanitize_path._table
    except AttributeError:
        path_sanitization_dict = {c: '' for c in '*;?<>"'}
        path_sanitization_dict.update({'/': '_', ':': '-', '\\': '_', '|': '-'})
        table = sanitize_path._table = str.maketrans(path_sanitization_dict)
    return text.translate(table)


def _trim_prefix(basename: str) -> str:
    try:
        prefix_match = _trim_prefix._prefix_match
    except AttributeError:
        prefix_match = _trim_prefix._prefix_match = re.compile(r'\d+\.?\s*(.*)').match

    if m := prefix_match(basename):
        basename = m.group(1)
    return basename


def plex_track_path(track_or_rel_path: Track | str, root: PathLike, strip_prefix: str | None = None) -> Path:
    if isinstance(track_or_rel_path, str):
        rel_path = track_or_rel_path
    else:
        rel_path = track_or_rel_path.media[0].parts[0].file

    if strip_prefix and rel_path.startswith(strip_prefix):
        rel_path = rel_path[len(strip_prefix):]

    if ON_WINDOWS and (root_str := root.as_posix() if isinstance(root, Path) else root).startswith('/'):
        # Path requires 2 parts for a leading // to be preserved on Windows.  If the root is for a network location
        # and has only 1 part, the additional leading / is always stripped.
        if not root_str.startswith('//'):
            root_str = '/' + root_str
        if root_str.endswith('/'):
            root_str = root_str[:-1]
        return Path(root_str + ('' if rel_path.startswith('/') else '/') + rel_path)
    else:
        return Path(root).joinpath(rel_path[1:] if rel_path.startswith('/') else rel_path)
