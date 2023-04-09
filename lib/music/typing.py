"""
Typing helpers.
"""

from pathlib import Path
from typing import TYPE_CHECKING, Iterable, Union, Optional, Any, Collection

if TYPE_CHECKING:
    from .files.album import AlbumDir  # noqa
    from .manager.update import AlbumInfo  # noqa

StrOrStrs = Union[str, Iterable[str], None]
StrIter = Iterable[str]
Strings = Collection[str]
OptStr = Optional[str]
OptInt = Optional[int]

Bool = Union[bool, Any]
PathLike = Union[Path, str]

AnyAlbum = Union['AlbumDir', 'AlbumInfo']
