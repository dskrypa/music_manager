r"""
Tkinter GUI base popups

:author: Doug Skrypa
"""

from __future__ import annotations

import logging
from concurrent.futures import Future
from functools import cached_property
from queue import Queue
from threading import current_thread, main_thread
from typing import TYPE_CHECKING, Union, Collection, Mapping

from ..elements import Input, Button
from ..positioning import positioner
from ..style import Style, StyleSpec
from ..utils import max_line_len
from ..window import Window

if TYPE_CHECKING:
    from ..typing import XY, Layout, Bool

__all__ = ['Popup', 'POPUP_QUEUE', 'BasicPopup']
log = logging.getLogger(__name__)

POPUP_QUEUE = Queue()


class Popup:
    def __init__(
        self,
        layout: Layout = (),
        title: str = None,
        *,
        parent: Window = None,
        bind_esc: Bool = False,
        keep_on_top: Bool = True,
        can_minimize: Bool = False,
        **kwargs
    ):
        self.title = title
        self.layout = layout
        self.parent = parent
        kwargs['keep_on_top'] = keep_on_top
        kwargs['can_minimize'] = can_minimize
        binds = kwargs.setdefault('binds', {})
        if bind_esc:
            binds['<Escape>'] = 'exit'
        self.window_kwargs = kwargs

    def get_layout(self) -> Layout:
        return self.layout

    def prepare_window(self) -> Window:
        return Window(self.get_layout(), title=self.title, **self.window_kwargs)

    @cached_property
    def window(self) -> Window:
        window = self.prepare_window()
        if parent := self.parent:
            window.move_to_center(parent)
        return window

    def _run(self):
        self.window.take_focus()
        self.window.run()
        return self.window.results

    def run(self):
        if current_thread() == main_thread():
            return self._run()

        future = Future()
        POPUP_QUEUE.put((future, self._run, (), {}))
        return future.result()


class BasicPopup(Popup):
    def __init__(
        self,
        text: str,
        *,
        button: Union[str, Button] = None,
        buttons: Union[Mapping[str, str], Collection[str], Collection[Button]] = None,
        multiline: Bool = False,
        style: StyleSpec = None,
        **kwargs,
    ):
        if buttons and button:
            raise ValueError('Use "button" or "buttons", not both')
        elif not buttons and not button:
            button = 'OK'
        super().__init__(**kwargs)
        self.text = text
        self.buttons = (button,) if button else buttons
        self.multiline = multiline
        self.style = Style.get_style(style)

    @cached_property
    def lines(self) -> list[str]:
        return self.text.splitlines()

    @cached_property
    def text_size(self) -> XY:
        if size := self.window_kwargs.pop('size', None):
            return size
        lines = self.lines
        n_lines = len(lines)
        if self.multiline or n_lines > 1:
            if parent := self.parent:
                monitor = positioner.get_monitor(*parent.position)
            else:
                monitor = positioner.get_monitor(0, 0)

            lines_to_show = max(1, min(monitor.height // self.style.char_height(), n_lines) + 1)
        else:
            lines_to_show = 1

        return max_line_len(lines), lines_to_show

    def prepare_buttons(self) -> Collection[Button]:
        buttons = self.buttons
        if all(isinstance(button, Button) for button in buttons):
            return buttons

        n_buttons = len(buttons)
        if n_buttons == 1:
            sides = ('right',)
            anchors = (None,)
        elif n_buttons == 2:
            sides = ('left', 'right')
            anchors = (None, None)
        elif n_buttons == 3:
            sides = ('left', 'left', 'left')
            anchors = ('left', 'center', 'right')
        else:
            sides = anchors = ('left' for _ in buttons)

        # log.debug(f'Preparing {buttons=} with {anchors=}, {sides=}')
        if isinstance(buttons, Mapping):
            buttons = [Button(v, key=k, anchor=a, side=s) for a, s, (k, v) in zip(anchors, sides, buttons.items())]
        else:
            buttons = [Button(val, key=val, anchor=a, side=s) for a, s, val in zip(anchors, sides, buttons)]

        return buttons

    def get_layout(self) -> Layout:
        return [[Input(self.text, disabled=True)], self.prepare_buttons()]
