"""
Tkinter GUI element utils

:author: Doug Skrypa
"""

from __future__ import annotations

from tkinter import TclError, Entry, Text, BaseWidget
from typing import TYPE_CHECKING, Optional, Union, Iterator

if TYPE_CHECKING:
    from ..typing import XY

__all__ = ['normalize_underline', 'get_selection_pos', 'find_descendants', 'get_top_level']


def normalize_underline(underline: Union[str, int], label: str) -> Optional[int]:
    try:
        return int(underline)
    except (TypeError, ValueError):
        pass
    try:
        return label.index(underline)
    except (ValueError, TypeError):
        return None


def get_selection_pos(
    widget: Union[Entry, Text], raw: bool = False
) -> Union[XY, tuple[XY, XY], tuple[None, None], tuple[str, str]]:
    try:
        first, last = widget.index('sel.first'), widget.index('sel.last')
    except (AttributeError, TclError):
        return None, None
    if raw:
        return first, last
    try:
        return int(first), int(last)
    except ValueError:
        pass
    first_line, first_index = map(int, first.split('.', 1))
    last_line, last_index = map(int, last.split('.', 1))
    return (first_line, first_index), (last_line, last_index)


def find_descendants(widget: BaseWidget) -> Iterator[BaseWidget]:
    for child in widget.children.values():
        yield child
        yield from find_descendants(child)


def get_top_level(widget: BaseWidget) -> BaseWidget:
    name = widget._w  # noqa
    return widget.nametowidget('.!'.join(name.split('.!')[:2]))
