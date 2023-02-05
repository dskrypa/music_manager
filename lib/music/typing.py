"""
Typing helpers.
"""

from pathlib import Path
from typing import Iterable, Union, Optional, Any

StrOrStrs = Union[str, Iterable[str], None]
OptStr = Optional[str]
StrIter = Iterable[str]
Bool = Union[bool, Any]
PathLike = Union[Path, str]
