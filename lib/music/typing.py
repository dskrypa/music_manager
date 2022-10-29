"""
Typing helpers.
"""

from typing import Iterable, Union, Optional, Any

StrOrStrs = Union[str, Iterable[str], None]
OptStr = Optional[str]
StrIter = Iterable[str]
Bool = Union[bool, Any]
