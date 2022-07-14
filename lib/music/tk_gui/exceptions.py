"""
Tkinter GUI Exceptions

:author: Doug Skrypa
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .elements import Element
    from .typing import Key
    from .window import Window

__all__ = ['TkGuiException', 'DuplicateKeyError']


class TkGuiException(Exception):
    """Base exception for errors in Tkinter GUI"""


class DuplicateKeyError(TkGuiException):
    """Raised when a duplicate key is used for an Element"""

    def __init__(self, key: Key, old: Element, new: Element, window: Window):
        self.key = key
        self.old = old
        self.new = new
        self.window = window

    def __str__(self) -> str:
        return (
            f'Invalid key={self.key!r} for element={self.new!r} in window={self.window!r}'
            f' - it is already associated with element={self.old!r}'
        )
