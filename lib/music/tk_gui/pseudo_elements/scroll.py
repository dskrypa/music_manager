"""
Tkinter GUI Scroll Bar Utils

:author: Doug Skrypa
"""

from __future__ import annotations

import logging
import re
import tkinter.constants as tkc
from abc import ABC
from functools import cached_property
from itertools import count
from tkinter import BaseWidget, Frame, LabelFrame, Canvas, Widget, Event, Tk, Toplevel, Text, Listbox
from tkinter.ttk import Scrollbar, Treeview
from typing import TYPE_CHECKING, Type, Mapping, Union, Optional, Any, Iterator

from ..utils import ON_WINDOWS

if TYPE_CHECKING:
    from ..style import Style
    from ..typing import Bool, BindCallback, Axis, XY

__all__ = [
    'add_scroll_bar',
    'ScrollableToplevel', 'ScrollableFrame', 'ScrollableLabelFrame',
    'ScrollableTreeview', 'ScrollableText', 'ScrollableListbox',
]
log = logging.getLogger(__name__)

FrameLike = Union[Tk, Frame, LabelFrame]
ScrollOuter = Union[BaseWidget, 'ScrollableBase', 'ScrollableContainer']

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
        # Additional possible kwargs: elementborderwidth, jump, repeatdelay, repeatinterval
        kwargs.update(pack_kwargs)
    scroll_bar.pack(**kwargs)

    return scroll_bar


class ScrollableBase(ABC):
    _tk_w_cls_search = re.compile(r'^(.*?)\d*$').search
    _counter = count()
    _scrollable_cls_names = set()
    _scroll_id: int
    _tk_cls: Type[Union[Widget, Toplevel]] = None
    scroll_bar_y: Optional[Scrollbar] = None
    scroll_bar_x: Optional[Scrollbar] = None

    def __init_subclass__(cls, tk_cls: Type[Union[Widget, Toplevel]] = None):  # noqa
        cls._tk_cls = tk_cls
        cls._scrollable_cls_names.add(cls.__name__.lower())

    def __init__(self: Union[Widget, Toplevel, ScrollableBase], *args, **kwargs):
        if (parent := self._tk_cls) is not None:
            parent.__init__(self, *args, **kwargs)
        else:
            super().__init__(*args, **kwargs)
        self._scroll_id = c = next(self._counter)
        self.scroll_id = f'{self.__class__.__name__}#{c}'

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__}[{self._scroll_id}, parent={self.scroll_parent!r}]>'

    @cached_property
    def scroll_parent(self: Union[ScrollableBase, BaseWidget]) -> Optional[ScrollableBase]:
        self_id: str = self._w  # noqa
        id_parts = self_id.split('.!')[:-1]
        for i, id_part in enumerate(reversed(id_parts)):
            if (m := self._tk_w_cls_search(id_part)) and m.group(1) in self._scrollable_cls_names:
                return self.nametowidget('.!'.join(id_parts[:-i]))
        return None

    @cached_property
    def scroll_parents(self) -> list[ScrollableBase]:
        parents = []
        sc = self
        while parent := sc.scroll_parent:
            parents.append(parent)
            sc = parent
        return parents

    @cached_property
    def scroll_children(self: Union[ScrollableContainer, BaseWidget]) -> list[ScrollableBase]:
        children = []
        all_children = self.winfo_children()
        while all_children:
            child = all_children.pop()
            if isinstance(child, ScrollableBase):
                children.append(child)
            else:
                all_children.extend(child.winfo_children())
        return children

    def _widgets(self) -> Iterator[BaseWidget]:
        yield self
        if (scroll_bar_y := self.scroll_bar_y) is not None:
            yield scroll_bar_y
        if (scroll_bar_x := self.scroll_bar_x) is not None:
            yield scroll_bar_x

    @cached_property
    def widgets(self) -> tuple[BaseWidget]:
        return tuple(self._widgets())


def get_scrollable(widget: Widget) -> Optional[ScrollableBase]:
    while widget:
        if isinstance(widget, ScrollableBase):
            return widget

        if (parent_name := widget.winfo_parent()) == '.':
            break
        widget = widget.nametowidget(parent_name)

    return None


def find_scroll_cb(event: Event, axis: Axis) -> Optional[BindCallback]:
    if not (scrollable := get_scrollable(event.widget)):  # Another window, or scrolling away from a scrollable area
        return None
    elif not isinstance(scrollable, ScrollableContainer):  # it's a ScrollableWidget
        return None
    elif not getattr(scrollable, f'scroll_bar_{axis}'):  # no scroll bar for this axis is configured
        return None
    # log.debug(f'Returning {axis} scroll func for {scrollable=}')
    return getattr(scrollable, f'scroll_{axis}')


def _scroll_y(event: Event):
    if cb := find_scroll_cb(event, 'y'):
        cb(event)


def _scroll_x(event: Event):
    if cb := find_scroll_cb(event, 'x'):
        cb(event)


# region Scrollable Container


class ScrollableContainer(ScrollableBase, ABC):
    _y_bind, _x_bind = ('<MouseWheel>', 'Shift-MouseWheel') if ON_WINDOWS else ('<4>', '<5>')
    _inner_widget_id: int
    # _y_bind_id: Optional[str] = None
    # _x_bind_id: Optional[str] = None
    canvas: Canvas
    inner_widget: FrameLike

    def __init__(
        self: Union[Widget, Toplevel, ScrollableContainer],
        parent: Optional[BaseWidget] = None,
        scroll_y: Bool = False,
        scroll_x: Bool = False,
        inner_cls: Type[FrameLike] = Frame,
        style: Style = None,
        inner_kwargs: dict[str, Any] = None,
        pad: XY = None,
        **kwargs,
    ):
        if 'relief' not in kwargs:
            kwargs.setdefault('borderwidth', 0)
        kwargs.setdefault('highlightthickness', 0)
        super().__init__(parent, **kwargs)
        self.init_canvas(scroll_y, scroll_x, style, pad)
        self.init_inner(inner_cls, scroll_y, scroll_x, **(inner_kwargs or {}))

    def init_canvas(
        self: ScrollOuter, scroll_y: Bool = False, scroll_x: Bool = False, style: Style = None, pad: XY = None
    ):
        kwargs = style.get_map('frame', background='bg') if style else {}
        self.canvas = canvas = Canvas(self, borderwidth=0, highlightthickness=0, **kwargs)
        if scroll_x:
            self.scroll_bar_x = add_scroll_bar(self, canvas, 'x', style, {'expand': 'false'})
        if scroll_y:
            self.scroll_bar_y = add_scroll_bar(self, canvas, 'y', style, {'fill': 'both', 'expand': True})

        kwargs = {'side': 'left', 'fill': 'both', 'expand': True}
        try:
            kwargs['padx'], kwargs['pady'] = pad
        except TypeError:
            pass
        canvas.pack(**kwargs)
        canvas.xview_moveto(0)
        canvas.yview_moveto(0)

    def init_inner(self: ScrollOuter, cls: Type[FrameLike], scroll_y: Bool = False, scroll_x: Bool = False, **kwargs):
        if 'relief' not in kwargs:
            kwargs.setdefault('borderwidth', 0)
        kwargs.setdefault('highlightthickness', 0)
        canvas = self.canvas
        self.inner_widget = inner_widget = cls(canvas, **kwargs)
        self._inner_widget_id = canvas.create_window(0, 0, window=inner_widget, anchor='nw')
        if scroll_y or scroll_x:
            canvas.bind_all(self._y_bind, _scroll_y, add='+')
            canvas.bind_all(self._x_bind, _scroll_x, add='+')
            # canvas.bind('<Enter>', self.hook_mouse_scroll)
            # canvas.bind('<Leave>', self.unhook_mouse_scroll)
            self.bind('<Configure>', self.set_scroll_region)

    def resize_inner(self, event: Event):
        self.canvas.itemconfigure(self._inner_widget_id, width=event.width, height=event.height)

    # def hook_mouse_scroll(self, event: Event):
    #     log.debug(f'Hooking mouse scroll for {self!r} due to {event=}, {self.scroll_children=}')
    #     canvas = self.canvas
    #     self._y_bind_id = canvas.bind_all(self._y_bind, self.scroll_y, add='+')
    #     self._x_bind_id = canvas.bind_all(self._x_bind, self.scroll_x, add='+')
    #
    # def unhook_mouse_scroll(self, event: Event = None):
    #     log.debug(f'Unhooking mouse scroll for {self!r} due to {event=}')
    #     canvas = self.canvas
    #     self._y_bind_id = canvas.unbind(self._y_bind, self._y_bind_id)  # using no return as a shortcut to set to None
    #     self._x_bind_id = canvas.unbind(self._x_bind, self._x_bind_id)
    #     if parent := self.scroll_parent:
    #         parent.hook_mouse_scroll(event)

    def scroll_y(self, event: Event):
        if (event.num == 5 or event.delta < 0) and (canvas := self.canvas).yview() != (0, 1):
            # TODO: event.delta / 120 units?
            canvas.yview_scroll(4, 'units')
        elif (event.num == 4 or event.delta > 0) and (canvas := self.canvas).yview() != (0, 1):
            canvas.yview_scroll(-4, 'units')

    def scroll_x(self, event: Event):
        if event.num == 5 or event.delta < 0:
            self.canvas.xview_scroll(4, 'units')
        elif event.num == 4 or event.delta > 0:
            self.canvas.xview_scroll(-4, 'units')

    def set_scroll_region(self, event: Event = None):
        canvas = self.canvas
        bbox = canvas.bbox('all')
        if canvas['scrollregion'] != '{} {} {} {}'.format(*bbox):
            # log.debug(f'Updating scroll region to {bbox=} != {canvas["scrollregion"]=} for {self}')
            canvas.configure(scrollregion=bbox)

    @cached_property
    def widgets(self) -> list[BaseWidget]:
        return [self.canvas, self.inner_widget, *self._widgets()]


class ScrollableToplevel(ScrollableContainer, Toplevel, tk_cls=Toplevel):
    pass


class ScrollableFrame(ScrollableContainer, Frame, tk_cls=Frame):
    pass


class ScrollableLabelFrame(ScrollableContainer, LabelFrame, tk_cls=LabelFrame):
    pass


# endregion

# region Scrollable Widget


class ScrollableWidget(ScrollableBase, ABC):
    _inner_cls: Type[Widget]

    def __init_subclass__(cls, inner_cls: Type[Widget], **kwargs):  # noqa
        super().__init_subclass__(**kwargs)
        cls._inner_cls = inner_cls

    def __init__(
        self, parent: BaseWidget = None, scroll_y: Bool = False, scroll_x: Bool = False, style: Style = None, **kwargs
    ):
        super().__init__(parent)
        self.inner_widget = inner_widget = self._inner_cls(self, **kwargs)
        if scroll_x:
            self.scroll_bar_x = add_scroll_bar(self, inner_widget, 'x', style)
        if scroll_y:
            self.scroll_bar_y = add_scroll_bar(self, inner_widget, 'y', style)
        inner_widget.pack(side='left', fill='both', expand=True, padx=0, pady=0)

    @cached_property
    def widgets(self) -> list[BaseWidget]:
        return [self.inner_widget, *self._widgets()]


class ScrollableTreeview(ScrollableWidget, Frame, tk_cls=Frame, inner_cls=Treeview):
    inner_widget: Treeview


class ScrollableText(ScrollableWidget, Frame, tk_cls=Frame, inner_cls=Text):
    inner_widget: Text

    def __init__(self, parent: BaseWidget = None, scroll_y: Bool = False, scroll_x: Bool = False, *args, **kwargs):
        super().__init__(parent, scroll_y, scroll_x, *args, **kwargs)
        self.inner_widget.configure(wrap=tkc.NONE if scroll_x else tkc.WORD)


class ScrollableListbox(ScrollableWidget, Frame, tk_cls=Frame, inner_cls=Listbox):
    inner_widget: Listbox


# endregion
