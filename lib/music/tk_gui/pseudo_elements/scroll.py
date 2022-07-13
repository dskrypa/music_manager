"""
Tkinter GUI Scroll Bar Utils

:author: Doug Skrypa
"""

from __future__ import annotations

import tkinter.constants as tkc
from tkinter.ttk import Scrollbar
from typing import TYPE_CHECKING, Literal, Mapping, Any

if TYPE_CHECKING:
    from tkinter import Frame, Widget
    from ..style import Style

__all__ = ['add_scroll_bar']

Axis = Literal['x', 'y']
AXIS_DIR_SIDE = {'x': (tkc.HORIZONTAL, tkc.BOTTOM), 'y': (tkc.VERTICAL, tkc.RIGHT)}


def add_scroll_bar(
    frame: Frame,
    widget: Widget,
    axis: Axis,
    style: Style = None,
    pack_kwargs: Mapping[str, Any] = None,
) -> Scrollbar:
    direction, side = AXIS_DIR_SIDE[axis]
    if style:
        name, ttk_style = style.make_ttk_style(f'scroll_bar.{direction.title()}.TScrollbar')
    else:
        name = ttk_style = None

    scroll_bar = Scrollbar(frame, orient=direction, command=getattr(widget, f'{axis}view'), style=name)

    if style:
        kwargs = style.get_map(
            'scroll',
            troughcolor='trough_color', framecolor='frame_color', bordercolor='frame_color',
            width='bar_width', arrowsize='arrow_width', relief='relief',
        )
        ttk_style.configure(name, **kwargs)
        if (bg := style.scroll.bg.default) and (ac := style.scroll.arrow_color.default):
            bg_list = [('selected', bg), ('active', ac), ('background', bg), ('!focus', bg)]
            ac_list = [('selected', ac), ('active', bg), ('background', bg), ('!focus', ac)]
            ttk_style.map(name, background=bg_list, arrowcolor=ac_list)

    widget.configure(**{f'{axis}scrollcommand': scroll_bar.set})

    kwargs = {'side': side, 'fill': axis}
    if pack_kwargs:
        kwargs.update(pack_kwargs)
    scroll_bar.pack(**kwargs)

    return scroll_bar
