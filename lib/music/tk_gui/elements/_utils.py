"""
Tkinter GUI element utils

:author: Doug Skrypa
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Union, Type, Any, Sequence

if TYPE_CHECKING:
    from ..typing import Bool, XY, EventCallback

__all__ = ['normalize_underline']


def normalize_underline(underline: Union[str, int], label: str) -> Optional[int]:
    try:
        return int(underline)
    except (TypeError, ValueError):
        pass
    try:
        return label.index(underline)
    except (ValueError, TypeError):
        return None
