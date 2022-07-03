"""
Tkinter GUI core Row and Element classes

:author: Doug Skrypa
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections import defaultdict
from functools import cached_property
from itertools import count
from tkinter import TclError
from typing import TYPE_CHECKING, Optional, Callable, Union, MutableMapping

from ..pseudo_elements.tooltips import ToolTip
from ..style import Style, Font, StyleSpec
from ..utils import Anchor, Inheritable, XY, BindCallback

if TYPE_CHECKING:
    from tkinter import Widget, Event
    from ..core import Window
    from ..pseudo_elements import ContextualMenu, Row

__all__ = ['Element']
log = logging.getLogger(__name__)


class Element(ABC):
    _counters = defaultdict(count)
    _tooltip: Optional[ToolTip] = None
    parent: Optional[Row] = None
    widget: Optional[Widget] = None
    tooltip_text: Optional[str] = None
    right_click_menu: Optional[ContextualMenu] = None
    left_click_cb: Optional[Callable] = None
    binds: Optional[MutableMapping[str, BindCallback]] = None

    pad = Inheritable('element_padding')                            # type: XY
    size = Inheritable('element_size')                              # type: XY
    auto_size_text = Inheritable()                                  # type: bool
    justify = Inheritable('element_justification', type=Anchor)     # type: Anchor
    style = Inheritable()                                           # type: Style

    def __init__(
        self,
        *,
        size: XY = None,
        pad: XY = None,
        style: StyleSpec = None,
        font: Font = None,
        auto_size_text: bool = None,
        border_width: int = None,
        justify: Union[str, Anchor] = None,
        visible: bool = True,
        tooltip: str = None,
        ttk_theme: str = None,
        bg: str = None,
        text_color: str = None,
        right_click_menu: ContextualMenu = None,
        left_click_cb: Callable = None,
        binds: MutableMapping[str, BindCallback] = None,
    ):
        self.id = next(self._counters[self.__class__])
        self._visible = visible

        # Directly stored attrs that override class defaults
        if tooltip:
            self.tooltip_text = tooltip
        if right_click_menu:
            self.right_click_menu = right_click_menu
        if left_click_cb:
            self.left_click_cb = left_click_cb
        if binds:
            self.binds = binds

        # Inheritable attrs
        self.pad = pad
        self.size = size
        self.auto_size_text = auto_size_text
        self.justify = justify
        self.style = Style.get(style)
        # if any(val is not None for val in (text_color, bg, font, ttk_theme, border_width)):
        if not (text_color is bg is font is ttk_theme is border_width is None):
            self.style = Style(
                parent=self.style, font=font, ttk_theme=ttk_theme, text=text_color, bg=bg, border_width=border_width
            )

    def __repr__(self) -> str:
        x, y = self.col_row
        return f'<{self.__class__.__name__}[id={self.id}, col={x}, row={y}, size={self.size}, visible={self._visible}]>'

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

    # endregion

    # region Pack Methods / Attributes

    @cached_property
    def anchor(self):
        return self.justify.value

    @property
    def pad_kw(self) -> dict[str, int]:
        try:
            x, y = self.pad
        except TypeError:
            x, y = 5, 3
        return {'padx': x, 'pady': y}

    def pack_into_row(self, row: Row):
        self.parent = row
        self.pack_into(row)
        self.apply_binds()
        if tooltip := self.tooltip_text:
            self.add_tooltip(tooltip)

    @abstractmethod
    def pack_into(self, row: Row):
        raise NotImplementedError

    def add_tooltip(
        self, text: str, delay: int = ToolTip.DEFAULT_DELAY, style: StyleSpec = None, wrap_len_px: int = None
    ):
        if self._tooltip:
            del self._tooltip
        self._tooltip = ToolTip(self, text, delay=delay, style=style, wrap_len_px=wrap_len_px)

    # endregion

    # region Visibility Methods

    def hide(self):
        self.widget.pack_forget()
        self._visible = False

    def show(self):
        self.widget.pack(**self.pad_kw)
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
