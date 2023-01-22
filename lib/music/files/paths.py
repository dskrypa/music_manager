"""
:author: Doug Skrypa
"""

from __future__ import annotations

from itertools import chain
from abc import ABC, abstractmethod
from functools import cached_property
from pathlib import Path
from typing import Iterable, Union

__all__ = ['FileBasedObject', 'SafePath', 'sanitize_path']

PathLike = Union[Path, str]


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

    def __repr__(self):
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
            return self.path.relative_to(Path('.').resolve()).as_posix()
        except Exception:
            return self.path.as_posix()

    def basename(self, no_ext=False, trim_prefix=False) -> str:
        basename = self.path.stem if no_ext else self.path.name
        return _trim_prefix(basename) if trim_prefix else basename

    @cached_property
    def ext(self) -> str:
        return self.path.suffix[1:]

    def __fspath__(self):
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
        import re
        prefix_match = _trim_prefix._prefix_match = re.compile(r'\d+\.?\s*(.*)').match
    if m := prefix_match(basename):
        basename = m.group(1)
    return basename
