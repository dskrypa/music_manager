"""

"""

from __future__ import annotations

from typing import Literal

from tk_gui.elements import Button, ButtonAction

__all__ = ['nav_button']


def nav_button(side: Literal['left', 'right'], key: str = None, **kwargs) -> Button:
    text, anchor = ('\u2770', 'w') if side == 'left' else ('\u2771', 'e')
    if not key:
        key = 'prev_view' if side == 'left' else 'next_view'
    kwargs.setdefault('action', ButtonAction.BIND_EVENT)
    return Button(text, key=key, size=(1, 2), pad=(0, 0), font=('Helvetica', 60), anchor=anchor, side=side, **kwargs)
