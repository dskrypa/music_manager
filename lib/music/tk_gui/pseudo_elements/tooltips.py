"""
Tkinter GUI Tooltips

:author: Doug Skrypa
"""

from __future__ import annotations

import logging
import tkinter.constants as tkc
from tkinter import Toplevel, TclError, Event, Label
from typing import TYPE_CHECKING, Optional

from ..style import Style, StyleSpec

if TYPE_CHECKING:
    from ..core import Element
    from ..typing import XY

__all__ = ['ToolTip']
log = logging.getLogger(__name__)


class ToolTip:
    """Based on https://stackoverflow.com/a/36221216/19070573"""
    DEFAULT_DELAY = 400
    DEFAULT_OFFSET = (0, -20)
    __slots__ = ('parent', 'text', 'delay', 'wrap_len_px', 'style', '_schedule_id', '_tip_window')

    def __init__(
        self, element: Element, text: str, delay: int = DEFAULT_DELAY, style: StyleSpec = None, wrap_len_px: int = None
    ):
        """
        :param element: The Element with which this ToolTip is associated
        :param text: The text to show
        :param delay: Delay in milliseconds after the mouse starts hovering, before the tooltip is shown
        :param style: The :class:`.Style` to use for this ToolTip
        :param wrap_len_px: Length, in pixels, after which lines should be wrapped
        """
        self.parent = element
        self.text = text
        self.delay = delay
        self.wrap_len_px = wrap_len_px
        self.style = Style.get_style(style) if style else None
        self._schedule_id: Optional[str] = None
        self._tip_window: Optional[Toplevel] = None
        widget = element.widget
        widget.bind('<Enter>', self.on_hover)
        widget.bind('<Leave>', self.on_leave)
        widget.bind('<ButtonPress>', self.on_leave)

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__}[parent={self.parent!r}, text={self.text!r}]>'

    def schedule(self, position: XY = None):
        self.cancel()
        self._schedule_id = self.parent.widget.after(self.delay, self.show, position or (0, 0))

    def cancel(self):
        if schedule_id := self._schedule_id:
            self.parent.widget.after_cancel(schedule_id)
            self._schedule_id = None

    def show(self, position: XY):
        if self._tip_window:
            return

        widget = self.parent.widget
        self._tip_window = tip_window = Toplevel(widget)
        try:
            tip_window.wm_overrideredirect(True)  # Keep the label, but hide the Toplevel (window)
        except (TclError, RuntimeError):
            log.error(f'Error using wm_overrideredirect for {self}', exc_info=True)

        x = widget.winfo_rootx() + position[0] + self.DEFAULT_OFFSET[0]
        y = widget.winfo_rooty() + position[1] + self.DEFAULT_OFFSET[1]
        tip_window.wm_geometry(f'+{x}+{y}')
        tip_window.wm_attributes('-topmost', 1)

        style = self.style or self.parent.style
        kwargs = style.get_map('tooltip', foreground='fg', background='bg', font='font')
        label = Label(
            tip_window,
            text=self.text,
            justify=tkc.LEFT,
            relief=tkc.SOLID,
            borderwidth=1,
            wraplength=self.wrap_len_px,
            **kwargs,
        )
        label.pack()

    def hide(self):
        if tip_window := self._tip_window:
            tip_window.destroy()
            self._tip_window = None

    def on_hover(self, event: Event):
        self.schedule((event.x, event.y))

    def on_leave(self, event: Event = None):
        self.cancel()
        self.hide()

    def __del__(self):
        self.on_leave()
