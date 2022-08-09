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
from typing import TYPE_CHECKING, Union, Optional, Collection, Mapping, Callable, Literal, Any

from ..elements import Element, Button, Text, Image, Input
from ..positioning import positioner
from ..style import Style, StyleSpec
from ..utils import max_line_len
from ..window import Window

if TYPE_CHECKING:
    from tkinter import Event
    from ..typing import XY, Layout, Bool, ImageType, Key

__all__ = ['Popup', 'POPUP_QUEUE', 'BasicPopup', 'BoolPopup', 'TextPromptPopup', 'LoginPromptPopup']
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

    @classmethod
    def as_callback(cls, *args, **kwargs) -> Callable:
        def callback(event: Event = None):
            return cls(*args, **kwargs).run()

        return callback

    def get_layout(self) -> Layout:
        return self.layout

    def prepare_window(self) -> Window:
        return Window(self.get_layout(), title=self.title, is_popup=True, **self.window_kwargs)

    @cached_property
    def window(self) -> Window:
        window = self.prepare_window()
        if parent := self.parent:
            window.move_to_center(parent)
        return window

    def _run(self) -> dict[Key, Any]:
        with self.window(take_focus=True) as window:
            window.run()
            return window.results

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
        image: ImageType = None,
        image_size: XY = None,
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
        self.image = image
        self.image_size = image_size or (100, 100)

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

    def get_layout(self) -> list[list[Element]]:
        layout: list[list[Element]] = [[Text(self.text)], self.prepare_buttons()]
        if image := self.image:
            layout[0].insert(0, Image(image, size=self.image_size))

        return layout


class BoolPopup(BasicPopup):
    def __init__(
        self,
        text: str,
        true: str = 'OK',
        false: str = 'Cancel',
        order: Literal['TF', 'FT'] = 'FT',
        select: Optional[bool] = True,
        **kwargs,
    ):
        self.true_key = true
        self.false_key = false
        tf = order.upper() == 'TF'
        tside, fside = ('left', 'right') if tf else ('right', 'left')
        te, fe = (True, False) if select else (False, True) if select is False else (False, False)
        tb = Button(true, key=true, side=tside, bind_enter=te)
        fb = Button(false, key=false, side=fside, bind_enter=fe)
        buttons = (tb, fb) if tf else (fb, tb)
        super().__init__(text, buttons=buttons, **kwargs)

    def run(self) -> Optional[bool]:
        results = super().run()
        if results[self.true_key]:
            return True
        elif results[self.false_key]:
            return False
        return None  # exited without clicking either button


class TextPromptPopup(BasicPopup):
    input_key = 'input'

    def __init__(self, text: str, button_text: str = 'Submit', **kwargs):
        button = Button(button_text, side='right', bind_enter=True, focus=False)
        super().__init__(text, button=button, **kwargs)

    def get_layout(self) -> list[list[Element]]:
        layout = super().get_layout()
        layout.insert(1, [Input(key=self.input_key)])
        return layout

    def run(self) -> Optional[str]:
        results = super().run()
        return results[self.input_key]


class LoginPromptPopup(BasicPopup):
    user_key = 'username'
    pw_key = 'password'

    def __init__(self, text: str, button_text: str = 'Submit', password_char: str = '\u2b24', **kwargs):
        button = Button(button_text, side='right', bind_enter=True, focus=False)
        super().__init__(text, button=button, **kwargs)
        self.password_char = password_char

    def get_layout(self) -> list[list[Element]]:
        layout = super().get_layout()
        layout.insert(1, [Text('Username:'), Input(key=self.user_key, focus=True)])
        layout.insert(2, [Text('Password:'), Input(key=self.pw_key, password_char=self.password_char)])
        return layout

    def run(self) -> tuple[Optional[str], Optional[str]]:
        results = super().run()
        return results[self.user_key], results[self.pw_key]
