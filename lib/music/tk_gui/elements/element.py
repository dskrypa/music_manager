"""
Tkinter GUI core Row and Element classes

:author: Doug Skrypa
"""

from __future__ import annotations

import logging
import tkinter.constants as tkc
from abc import ABC, abstractmethod
from collections import defaultdict
from functools import cached_property
from itertools import count
from tkinter import TclError
from typing import TYPE_CHECKING, Optional, Callable, Union, Any, MutableMapping, overload

from ..enums import StyleState, Anchor, Justify, Side, BindTargets
from ..pseudo_elements.tooltips import ToolTip
from ..style import Style, StyleSpec
from ..utils import Inheritable, ClearableCachedPropertyMixin, call_with_popped, extract_style, find_descendants

if TYPE_CHECKING:
    from tkinter import Widget, Event, BaseWidget
    from ..pseudo_elements.row import RowBase, Row
    from ..typing import XY, Bool, BindCallback, Key, TkFill, BindTarget
    from ..window import Window
    from .menu import Menu

__all__ = ['ElementBase', 'Element', 'Interactive']
log = logging.getLogger(__name__)

_DIRECT_ATTRS = {'key', 'right_click_menu', 'left_click_cb', 'binds', 'data'}
_INHERITABLES = {'size', 'auto_size_text', 'anchor', 'justify_text'}
_BASIC = {'style', 'pad', 'side', 'fill', 'expand', 'allow_focus'}
_Side = Union[str, Side]


class ElementBase(ClearableCachedPropertyMixin, ABC):
    _counters = defaultdict(count)
    _style_config: dict[str, Any]
    _id: int
    id: str
    parent: Optional[RowBase] = None
    column: Optional[int] = None
    widget: Optional[Widget] = None
    fill: TkFill = None
    expand: bool = None
    allow_focus: bool = False
    pad: XY = Inheritable('element_padding')
    side: Side = Inheritable('element_side', type=Side)
    style: Style = Inheritable(type=Style.get_style)

    def __init__(
        self,
        style: StyleSpec = None,
        pad: XY = None,
        side: _Side = None,
        fill: TkFill = None,
        expand: bool = None,
        **kwargs,
    ):
        cls = self.__class__
        self._id = _id = next(self._counters[cls])
        self.id = f'{cls.__name__}#{_id}'
        self.pad = pad
        self.side = side
        self._style_config = extract_style(kwargs) if kwargs else {}
        if (allow_focus := kwargs.pop('allow_focus', None)) is not None:
            self.allow_focus = allow_focus
        if kwargs:
            raise ValueError(f'Unexpected {kwargs=}')
        if expand is not None:
            self.expand = expand
        if fill:
            self.fill = fill
        if style:
            self.style = style

    # region Introspection

    @property
    def window(self) -> Window:
        return self.parent.window

    @property
    def size_and_pos(self) -> tuple[XY, XY]:
        widget = self.widget
        size, pos = widget.winfo_geometry().split('+', 1)
        w, h = size.split('x', 1)
        x, y = pos.split('+', 1)
        return (int(w), int(h)), (int(x), int(y))

    @cached_property
    def widgets(self) -> list[BaseWidget]:
        widget = self.widget
        return [widget, *find_descendants(widget)]

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
        self.pack_into(row, column)

    @abstractmethod
    def pack_into(self, row: RowBase, column: int):
        raise NotImplementedError

    def pack_widget(self, *, expand: bool = None, fill: TkFill = None, **kwargs):
        if expand is None:
            expand = self.expand
        if fill is None:
            fill = self.fill
        pack_kwargs = {  # Note: using pack_kwargs to allow things like padding overrides
            'side': self.side.value,
            'expand': False if expand is None else expand,
            'fill': tkc.NONE if not fill else tkc.BOTH if fill is True else fill,
            **self.pad_kw,
            **kwargs,
        }
        self.widget.pack(**pack_kwargs)

    # endregion


class Element(ElementBase, ABC):
    _key: Optional[Key] = None
    _tooltip: Optional[ToolTip] = None
    _pack_settings: dict[str, Any] = None
    tooltip_text: Optional[str] = None
    right_click_menu: Optional[Menu] = None
    left_click_cb: Optional[Callable] = None
    binds: Optional[MutableMapping[str, BindCallback]] = None
    bind_clicks: bool = None
    data: Any = None                                            # Any data that needs to be stored with the element

    size: XY = Inheritable('element_size')
    auto_size_text: bool = Inheritable()
    anchor: Anchor = Inheritable('anchor_elements', type=Anchor)
    justify_text: Justify = Inheritable('text_justification', type=Justify)

    @overload
    def __init__(
        self,
        *,
        key: Key = None,
        size: XY = None,
        pad: XY = None,
        style: StyleSpec = None,
        auto_size_text: Bool = None,
        anchor: Union[str, Anchor] = None,
        side: Union[str, Side] = Side.LEFT,
        justify_text: Union[str, Justify] = None,
        expand: Bool = None,
        fill: TkFill = None,
        allow_focus: bool = False,
        visible: Bool = True,
        tooltip: str = None,
        right_click_menu: Menu = None,
        left_click_cb: Callable = None,
        binds: MutableMapping[str, BindCallback] = None,
        bind_clicks: Bool = None,
        data: Any = None,
    ):
        ...

    def __init__(self, *, visible: Bool = True, bind_clicks: Bool = None, **kwargs):
        super().__init__(**{k: kwargs.pop(k, None) for k in _BASIC})
        self._visible = visible
        self._style_config = extract_style(kwargs)
        if tooltip_text := kwargs.pop('tooltip', None):
            self.tooltip_text = tooltip_text
        if bind_clicks is None:
            self.bind_clicks = bool(kwargs.get('right_click_menu') or kwargs.get('left_click_cb'))
        else:
            self.bind_clicks = bind_clicks

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
        return f'<{self.__class__.__name__}[id={self.id}, size={self.size}, visible={self._visible}]>'

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

    # region Pack Methods / Attributes

    @property
    def style_config(self) -> dict[str, Any]:
        return self._style_config

    def pack_into_row(self, row: RowBase, column: int):
        self.parent = row
        self.column = column
        if key := self._key:
            row.window.register_element(key, self)
        self.pack_into(row, column)
        self.apply_binds()
        if tooltip := self.tooltip_text:
            self.add_tooltip(tooltip)

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

        self._pack_widget(widget, expand, fill, kwargs)
        if focus:
            self.parent.window.maybe_set_focus(self, widget)
        if disabled:  # TODO: Handle state=disabled separately from readonly
            widget['state'] = 'readonly' if disabled is True else disabled

    def _pack_widget(self, widget: Widget, expand: bool, fill: TkFill, kwargs: dict[str, Any]):
        if expand is None:
            expand = self.expand
        if fill is None:
            fill = self.fill

        pack_kwargs = {  # Note: using pack_kwargs to allow things like padding overrides
            'side': self.side.value,
            'expand': False if expand is None else expand,
            'fill': tkc.NONE if not fill else tkc.BOTH if fill is True else fill,
            **self.pad_kw,
            **kwargs,
        }
        if anchor := self.anchor.value:
            try:
                widget.configure(anchor=anchor)  # noqa
            except TclError:  # Not all widgets support anchor in configure
                pack_kwargs['anchor'] = anchor

        widget.pack(**pack_kwargs)
        if not self._visible:
            widget.pack_forget()

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
        self._pack_settings = widget.pack_info()
        widget.pack_forget()
        self._visible = False

    def show(self):
        settings = self._pack_settings or {}
        self.widget.pack(**settings)
        # self.widget.pack(**self.pad_kw)
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
        if self.bind_clicks:
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

    def normalize_callback(self, cb: BindTarget) -> BindCallback:
        if isinstance(cb, str):
            cb = BindTargets(cb)
        if isinstance(cb, BindTargets):
            if cb == BindTargets.EXIT:
                cb = self.window.close
            elif cb == BindTargets.INTERRUPT:
                cb = self.trigger_interrupt
            elif cb == BindTargets.POPUP:
                cb = self.handle_open_popup
            else:
                raise ValueError(f'Invalid {cb=} for {self}')
        elif not isinstance(cb, Callable):
            raise TypeError(f'Invalid {cb=} for {self}')
        return cb

    # endregion

    # region Event Handling

    def trigger_interrupt(self, event: Event = None):
        self.window.interrupt(event, self)

    def handle_left_click(self, event: Event):
        # log.debug(f'Handling left click')
        if cb := self.left_click_cb:
            # log.debug(f'Passing {event=} to {cb=}')
            cb(event)

    def handle_right_click(self, event: Event):
        if menu := self.right_click_menu:
            menu.parent = self  # Needed for style inheritance
            menu.show(event, self.widget.master)  # noqa

    def handle_open_popup(self, event: Event):
        log.debug(f'No popup action is configured for {self}')

    # endregion


class InteractiveMixin:
    disabled: bool = False
    focus: bool = False
    valid: bool = True
    allow_focus: bool = True

    def init_interactive(self, disabled: Bool = False, focus: Bool = False, valid: Bool = True):
        self.disabled = disabled
        self.focus = focus
        self.valid = valid

    def init_interactive_from_kwargs(self, kwargs: dict[str, Any]):
        call_with_popped(self.init_interactive, ('disabled', 'focus', 'valid'), kwargs)

    @property
    def style_state(self) -> StyleState:
        if self.disabled:
            return StyleState.DISABLED
        elif not self.valid:
            return StyleState.INVALID
        return StyleState.DEFAULT

    def pack_widget(self, *, expand: bool = False, fill: TkFill = tkc.NONE, **kwargs):
        super().pack_widget(expand=expand, fill=fill, focus=self.focus, disabled=self.disabled, **kwargs)  # noqa


class Interactive(InteractiveMixin, Element, ABC):
    def __init__(self, disabled: Bool = False, focus: Bool = False, valid: Bool = True, **kwargs):
        super().__init__(**kwargs)
        self.init_interactive(disabled, focus, valid)
