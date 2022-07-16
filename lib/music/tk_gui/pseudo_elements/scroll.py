"""
Tkinter GUI Scroll Bar Utils

:author: Doug Skrypa
"""

from __future__ import annotations

import tkinter.constants as tkc
from tkinter import Misc, Frame, LabelFrame, Canvas, Widget, Event, Tk, Toplevel
from tkinter.ttk import Scrollbar, Treeview
from typing import TYPE_CHECKING, Literal, Type, Mapping, Union, Optional, Any
from weakref import WeakKeyDictionary

from ..utils import ON_WINDOWS

if TYPE_CHECKING:
    from ..style import Style
    from ..typing import Bool

__all__ = ['add_scroll_bar', 'ScrollableToplevel', 'ScrollableFrame', 'ScrollableTreeview']

FrameLike = Union[Tk, Frame, LabelFrame]
ScrollOuter = Union[Misc, 'Scrollable']
Axis = Literal['x', 'y']
AXIS_DIR_SIDE = {'x': (tkc.HORIZONTAL, tkc.BOTTOM), 'y': (tkc.VERTICAL, tkc.RIGHT)}


def add_scroll_bar(
    outer: ScrollOuter,
    inner: Widget,
    axis: Axis,
    style: Style = None,
    pack_kwargs: Mapping[str, Any] = None,
) -> Scrollbar:
    direction, side = AXIS_DIR_SIDE[axis]
    if style:
        name, ttk_style = style.make_ttk_style(f'scroll_bar.{direction.title()}.TScrollbar')
    else:
        name = ttk_style = None

    scroll_bar = Scrollbar(outer, orient=direction, command=getattr(inner, f'{axis}view'), style=name)

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

    inner.configure(**{f'{axis}scrollcommand': scroll_bar.set})

    kwargs = {'side': side, 'fill': axis}
    if pack_kwargs:
        kwargs.update(pack_kwargs)
    scroll_bar.pack(**kwargs)

    return scroll_bar


class ScrollableBase:
    _inner_outer_map = WeakKeyDictionary()
    _tk_cls: Type[Union[Widget, Toplevel]] = None
    scroll_bar_y: Optional[Scrollbar] = None
    scroll_bar_x: Optional[Scrollbar] = None

    def __init_subclass__(cls, tk_cls: Type[Union[Widget, Toplevel]] = None):  # noqa
        cls._tk_cls = tk_cls

    def __init__(self: Union[Widget, Toplevel, ScrollableBase], *args, **kwargs):
        if (parent := self._tk_cls) is not None:
            parent.__init__(self, *args, **kwargs)
        else:
            super().__init__(*args, **kwargs)


class Scrollable(ScrollableBase):
    _y_bind, _x_bind = ('<MouseWheel>', 'Shift-MouseWheel') if ON_WINDOWS else ('<4>', '<5>')
    _inner_widget_id: int
    canvas: Canvas
    inner_widget: FrameLike

    def __init__(
        self: Union[Widget, Toplevel, Scrollable],
        parent: Optional[Misc] = None,
        scroll_y: Bool = False,
        scroll_x: Bool = False,
        inner_cls: Type[FrameLike] = Frame,
        style: Style = None,
        inner_kwargs: dict[str, Any] = None,
        **kwargs,
    ):
        if 'relief' not in kwargs:
            kwargs.setdefault('borderwidth', 0)
        kwargs.setdefault('highlightthickness', 0)
        super().__init__(parent, **kwargs)
        self.init_canvas(scroll_y, scroll_x, style)
        self.init_inner(inner_cls, scroll_y, scroll_x, **(inner_kwargs or {}))

    def init_canvas(self: ScrollOuter, scroll_y: Bool = False, scroll_x: Bool = False, style: Style = None):
        self.canvas = canvas = Canvas(self, borderwidth=0, highlightthickness=0)
        if scroll_x:
            self.scroll_bar_x = add_scroll_bar(self, canvas, 'x', style, {'expand': 'false'})
        if scroll_y:
            self.scroll_bar_y = add_scroll_bar(self, canvas, 'y', style, {'fill': 'both', 'expand': True})

        canvas.pack(side='left', fill='both', expand=True)
        canvas.xview_moveto(0)
        canvas.yview_moveto(0)

    def init_inner(self: ScrollOuter, cls: Type[FrameLike], scroll_y: Bool = False, scroll_x: Bool = False, **kwargs):
        if 'relief' not in kwargs:
            kwargs.setdefault('borderwidth', 0)
        kwargs.setdefault('highlightthickness', 0)
        canvas = self.canvas
        self.inner_widget = inner_widget = cls(canvas, **kwargs)
        self._inner_widget_id = canvas.create_window(0, 0, window=inner_widget, anchor='nw')
        self._inner_outer_map[inner_widget] = self
        if scroll_y or scroll_x:
            canvas.bind('<Enter>', self.hook_mouse_scroll)
            canvas.bind('<Leave>', self.unhook_mouse_scroll)
            self.bind('<Configure>', self.set_scroll_region)

    def resize_inner(self, event: Event):
        self.canvas.itemconfigure(self._inner_widget_id, width=event.width, height=event.height)

    def hook_mouse_scroll(self, event: Event = None):
        canvas = self.canvas
        canvas.bind_all(self._y_bind, self.scroll_y, add='+')
        canvas.bind_all(self._x_bind, self.scroll_x, add='+')

    def unhook_mouse_scroll(self, event: Event = None):
        canvas = self.canvas
        canvas.unbind_all(self._y_bind)
        canvas.unbind_all(self._x_bind)

    def scroll_y(self: Union[Widget, Toplevel, Scrollable], event: Event):
        if (outer := self._inner_outer_map.get(event.widget)) and outer.scroll_bar_y:
            # log.debug(f'Ignoring Y axis scroll for {event=} due to {outer=} focus')
            return
        elif (event.num == 5 or event.delta < 0) and (canvas := self.canvas).yview() != (0, 1):
            canvas.yview_scroll(4, 'units')
        elif (event.num == 4 or event.delta > 0) and (canvas := self.canvas).yview() != (0, 1):
            canvas.yview_scroll(-4, 'units')

    def scroll_x(self, event: Event):
        if (outer := self._inner_outer_map.get(event.widget)) and outer.scroll_bar_x:
            return
        elif event.num == 5 or event.delta < 0:
            self.canvas.xview_scroll(4, 'units')
        elif event.num == 4 or event.delta > 0:
            self.canvas.xview_scroll(-4, 'units')

    def set_scroll_region(self, event: Event = None):
        canvas = self.canvas
        bbox = canvas.bbox('all')
        if canvas['scrollregion'] != '{} {} {} {}'.format(*bbox):
            # log.debug(f'Updating scroll region to {bbox=} != {canvas["scrollregion"]=} for {self}')
            canvas.configure(scrollregion=bbox)


class ScrollableToplevel(Scrollable, Toplevel, tk_cls=Toplevel):
    pass


class ScrollableFrame(Scrollable, Frame, tk_cls=Frame):
    pass


class ScrollableLabelFrame(Scrollable, LabelFrame, tk_cls=LabelFrame):
    pass


class ScrollableTreeview(ScrollableBase, Frame, tk_cls=Frame):
    inner_widget: Treeview

    def __init__(
        self, parent: Misc = None, scroll_y: Bool = False, scroll_x: Bool = False, style: Style = None, **kwargs
    ):
        super().__init__(parent)
        self.inner_widget = inner_widget = Treeview(self, **kwargs)
        self._inner_outer_map[inner_widget] = self
        if scroll_x:
            self.scroll_bar_x = add_scroll_bar(self, inner_widget, 'x', style)
        if scroll_y:
            self.scroll_bar_y = add_scroll_bar(self, inner_widget, 'y', style)
        inner_widget.pack(side='left', fill='both', expand=True, padx=0, pady=0)
