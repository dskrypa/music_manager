"""

"""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Any

from tk_gui.elements import Button, ButtonAction, Text

__all__ = ['nav_button', 'IText']


def nav_button(side: Literal['left', 'right'], key: str = None, **kwargs) -> Button:
    text, anchor = ('\u2770', 'w') if side == 'left' else ('\u2771', 'e')
    if not key:
        key = 'prev_view' if side == 'left' else 'next_view'
    kwargs.setdefault('action', ButtonAction.BIND_EVENT)
    return Button(text, key=key, size=(1, 2), pad=(0, 0), font=('Helvetica', 60), anchor=anchor, side=side, **kwargs)


def IText(value: Any = '', *args, **kwargs) -> Text:
    if isinstance(value, Path):
        value = value.as_posix()
    elif value is None:
        value = ''
    return Text(value, *args, use_input_style=True, **kwargs)
