"""
Typing helpers.
"""

from pathlib import Path
from typing import Iterable, Union, Optional, Any, Collection

StrOrStrs = Union[str, Iterable[str], None]
StrIter = Iterable[str]
Strings = Collection[str]
OptStr = Optional[str]
OptInt = Optional[int]

Bool = Union[bool, Any]
PathLike = Union[Path, str]
