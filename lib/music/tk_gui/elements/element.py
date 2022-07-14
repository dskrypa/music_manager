"""
Tkinter GUI core Row and Element classes

:author: Doug Skrypa
"""

from __future__ import annotations

import logging
import tkinter.constants as tkc
from abc import ABC, abstractmethod
from collections import defaultdict
from itertools import count
from tkinter import TclError, Frame, Text
from tkinter.ttk import Style as TtkStyle, Scrollbar
from typing import TYPE_CHECKING, Optional, Callable, Union, Any, MutableMapping, overload

from ..pseudo_elements.scroll import add_scroll_bar
from ..pseudo_elements.tooltips import ToolTip
from ..style import Style, StyleSpec, State
from ..utils import Anchor, Justify, Side, Inheritable, ClearableCachedPropertyMixin

if TYPE_CHECKING:
    from tkinter import Widget, Event
    from ..pseudo_elements import ContextualMenu, Row
    from ..typing import XY, BindCallback, Key, TkFill
    from ..window import Window

__all__ = ['Element', 'Interactive', 'ScrollableMixin']
log = logging.getLogger(__name__)

_DIRECT_ATTRS = {'key', 'tooltip', 'right_click_menu', 'left_click_cb', 'binds', 'expand', 'fill', 'data'}
_INHERITABLES = {'pad', 'size', 'auto_size_text', 'grid', 'side', 'anchor', 'justify_text', 'style'}


class ElementBase(ClearableCachedPropertyMixin, ABC):
    _counters = defaultdict(count)
    _id: int
    id: str
    ttk_styles: dict[str, TtkStyle]
    widget: Optional[Widget] = None
    style: Style = Inheritable(type=Style.get_style)

    def __init__(self, style: StyleSpec = None):
        cls = self.__class__
        self._id = _id = next(self._counters[cls])
        self.id = f'{cls.__name__}#{_id}'
        self.ttk_styles = {}
        if style:
            self.style = style

    # region TTK Styles

    def ttk_style_name(self, suffix: str) -> str:
        return f'{self.id}.{suffix}'

    def prepare_ttk_style(self, name_suffix: str) -> tuple[str, TtkStyle]:
        name = self.ttk_style_name(name_suffix)
        self.ttk_styles[name] = ttk_style = TtkStyle()
        ttk_style.theme_use(self.style.ttk_theme)
        return name, ttk_style

    # endregion


class Element(ElementBase, ABC):
    _key: Optional[Key] = None
    _tooltip: Optional[ToolTip] = None
    _pack_settings: dict[str, Any] = None
    parent: Optional[Row] = None
    column: Optional[int] = None
    tooltip_text: Optional[str] = None
    right_click_menu: Optional[ContextualMenu] = None
    left_click_cb: Optional[Callable] = None
    binds: Optional[MutableMapping[str, BindCallback]] = None
    data: Any = None                                            # Any data that needs to be stored with the element
    expand: bool = None
    fill: TkFill = None

    pad: XY = Inheritable('element_padding')
    size: XY = Inheritable('element_size')
    grid: bool = Inheritable()
    auto_size_text: bool = Inheritable()
    anchor: Anchor = Inheritable('anchor_elements', type=Anchor)
    justify_text: Justify = Inheritable('text_justification', type=Justify)
    side: Side = Inheritable('element_side', type=Side)

    @overload
    def __init__(
        self,
        *,
        key: Key = None,
        size: XY = None,
        pad: XY = None,
        style: StyleSpec = None,
        auto_size_text: bool = None,
        anchor: Union[str, Anchor] = None,
        side: Union[str, Side] = Side.LEFT,
        justify_text: Union[str, Justify] = None,
        grid: bool = None,
        expand: bool = None,
        fill: TkFill = None,
        visible: bool = True,
        tooltip: str = None,
        right_click_menu: ContextualMenu = None,
        left_click_cb: Callable = None,
        binds: MutableMapping[str, BindCallback] = None,
        data: Any = None,
    ):
        ...

    def __init__(self, *, visible: bool = True, style: StyleSpec = None, **kwargs):
        super().__init__(style)
        self._visible = visible

        bad = {}
        for key, val in kwargs.items():
            if key in _DIRECT_ATTRS:
                if val is not None:
                    setattr(self, key, val)
            elif key in _INHERITABLES:
                setattr(self, key, val)
            else:
                bad[key] = val
        if bad:
            raise ValueError(f'Invalid options for {self.__class__.__name__}: {bad}')

    def __repr__(self) -> str:
        x, y = self.col_row
        return f'<{self.__class__.__name__}[id={self.id}, col={x}, row={y}, size={self.size}, visible={self._visible}]>'

    @property
    def key(self) -> Key:
        if key := self._key:
            return key
        return self.id

    @key.setter
    def key(self, value: Key):
        self._key = value
        if parent := self.parent:
            parent.window.register_element(value, self)

    @property
    def value(self) -> Any:
        return None

    # region Introspection

    @property
    def window(self) -> Window:
        return self.parent.window

    @property
    def col_row(self) -> XY:
        row = self.parent
        x = row.elements.index(self)
        y = row.parent.rows.index(row)
        return x, y

    @property
    def size_and_pos(self) -> tuple[XY, XY]:
        widget = self.widget
        size, pos = widget.winfo_geometry().split('+', 1)
        w, h = size.split('x', 1)
        x, y = pos.split('+', 1)
        return (int(w), int(h)), (int(x), int(y))

    # endregion

    # region Pack Methods / Attributes

    @property
    def pad_kw(self) -> dict[str, int]:
        try:
            x, y = self.pad
        except TypeError:
            x, y = 5, 3
        return {'padx': x, 'pady': y}

    def pack_into_row(self, row: Row, column: int):
        self.parent = row
        self.column = column
        if key := self._key:
            row.window.register_element(key, self)
        self.pack_into(row, column)
        self.apply_binds()
        if tooltip := self.tooltip_text:
            self.add_tooltip(tooltip)

    @abstractmethod
    def pack_into(self, row: Row, column: int):
        raise NotImplementedError

    def pack_widget(
        self,
        *,
        expand: bool = None,
        fill: TkFill = None,
        focus: bool = False,
        disabled: bool = False,
        widget: Widget = None,
        **kwargs,
    ):
        if not widget:
            widget = self.widget

        if self.grid:
            self._grid_widget(widget, kwargs)
        else:
            self._pack_widget(widget, expand, fill, kwargs)

        if focus:
            widget.focus_set()
        if disabled:
            widget['state'] = 'readonly' if disabled is True else disabled

    def _pack_widget(self, widget: Widget, expand: bool, fill: TkFill, kwargs: dict[str, Any]):
        if expand is None:
            expand = self.expand
        if fill is None:
            fill = self.fill
        pack_kwargs = {  # Note: using pack_kwargs to allow things like padding overrides
            'anchor': self.anchor.value,
            'side': self.side.value,
            'expand': False if expand is None else expand,
            'fill': tkc.NONE if not fill else tkc.BOTH if fill is True else fill,
            **self.pad_kw,
            **kwargs,
        }
        widget.pack(**pack_kwargs)
        if not self._visible:
            widget.pack_forget()

    def _grid_widget(self, widget: Widget, kwargs: dict[str, Any]):
        widget.grid_configure(
            row=self.parent.num,
            column=self.column,
            sticky=self.anchor.as_sticky(),
            **self.pad_kw,
            **kwargs
        )
        if not self._visible:
            widget.grid_forget()

    def add_tooltip(
        self, text: str, delay: int = ToolTip.DEFAULT_DELAY, style: StyleSpec = None, wrap_len_px: int = None
    ):
        if self._tooltip:
            del self._tooltip
        self._tooltip = ToolTip(self, text, delay=delay, style=style, wrap_len_px=wrap_len_px)

    # endregion

    # region Visibility Methods

    def hide(self):
        widget = self.widget
        if self.grid:
            self._pack_settings = widget.grid_info()
            widget.grid_forget()
        else:
            self._pack_settings = widget.pack_info()
            widget.pack_forget()
        self._visible = False

    def show(self):
        widget = self.widget
        settings = self._pack_settings or {}
        if self.grid:
            widget.grid_configure(**settings)
            # widget.grid_configure(row=self.parent.num, column=self.column, **self.pad_kw)
        else:
            widget.pack(**settings)
            # widget.pack(**self.pad_kw)
        self._visible = True

    def toggle_visibility(self, show: bool = None):
        if show is None:
            show = not self._visible
        if show:
            self.show()
        else:
            self.hide()

    # endregion

    # region Bind Methods

    def apply_binds(self):
        widget = self.widget
        widget.bind('<Button-1>', self.handle_left_click)
        widget.bind('<Button-3>', self.handle_right_click)
        if self.binds:
            for event_pat, cb in self.binds.items():
                self._bind(event_pat, cb)

    def bind(self, event_pat: str, cb: BindCallback):
        if self.widget:
            self._bind(event_pat, cb)
        else:
            try:
                self.binds[event_pat] = cb
            except TypeError:  # self.binds is None
                self.binds = {event_pat: cb}

    def _bind(self, event_pat: str, cb: BindCallback):
        if cb is None:
            return
        log.debug(f'Binding event={event_pat!r} to {cb=}')
        try:
            self.widget.bind(event_pat, cb)
        except (TclError, RuntimeError) as e:
            log.error(f'Unable to bind event={event_pat!r}: {e}')
            self.widget.unbind_all(event_pat)

    # endregion

    # region Event Handlers

    def handle_left_click(self, event: Event):
        # log.debug(f'Handling left click')
        if cb := self.left_click_cb:
            # log.debug(f'Passing {event=} to {cb=}')
            cb(event)

    def handle_right_click(self, event: Event):
        if menu := self.right_click_menu:
            menu.show(event, self.widget.master)  # noqa

    # endregion


class Interactive(Element, ABC):
    def __init__(self, disabled: bool = False, focus: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.disabled = disabled
        self.focus = focus
        self.valid = True

    @property
    def style_state(self) -> State:
        if self.disabled:
            return State.DISABLED
        elif not self.valid:
            return State.INVALID
        return State.DEFAULT

    def pack_widget(self, *, expand: bool = False, fill: TkFill = tkc.NONE, **kwargs):
        super().pack_widget(expand=expand, fill=fill, focus=self.focus, disabled=self.disabled, **kwargs)


class ScrollableMixin:
    frame: Frame
    widget: Text
    style: Style
    scroll_bar_y: Optional[Scrollbar] = None
    scroll_bar_x: Optional[Scrollbar] = None

    def add_scroll_bars(self, vertical: bool = True, horizontal: bool = False):
        if vertical:
            self.add_scroll_bar(True)
        if horizontal:
            self.add_scroll_bar(False)

    def add_scroll_bar(self, vertical: bool = True):
        axis = 'y' if vertical else 'x'
        scroll_bar = add_scroll_bar(self.frame, self.widget, axis, self.style)  # noqa
        setattr(self, f'scroll_bar_{axis}', scroll_bar)
