"""
Tkinter GUI button elements

:author: Doug Skrypa
"""

from __future__ import annotations

import logging
import tkinter.constants as tkc
from enum import Enum
from math import ceil
from time import monotonic
from tkinter import Event, Button as _Button
from typing import TYPE_CHECKING, Union, MutableMapping

from PIL.ImageTk import PhotoImage

from ds_tools.images.utils import ImageType, as_image

from .element import Element
from ..utils import Justify

if TYPE_CHECKING:
    from ..pseudo_elements import Row
    from ..typing import XY, BindCallback, Bool

__all__ = ['Button']
log = logging.getLogger(__name__)

# fmt: off
STYLE_KEY_MAP = {
    'button_fg': 'foreground', 'button_bg': 'background',
    'hover_fg': 'activeforeground', 'hover_bg': 'activebackground',
    'focus_fg': 'highlightcolor', 'focus_bg': 'highlightbackground',
}
# fmt: on


class ButtonAction(Enum):
    SUBMIT = 'submit'

    @classmethod
    def _missing_(cls, value: str):
        try:
            return cls[value.upper()]
        except KeyError:
            return None


class Button(Element):
    widget: _Button
    separate: bool = False
    bind_enter: bool = False

    def __init__(
        self,
        text: str = '',
        image: ImageType = None,
        *,
        disabled: Bool = False,
        focus: Bool = False,
        shortcut: str = None,
        justify_text: Union[str, Justify, None] = Justify.CENTER,
        action: Union[ButtonAction, str] = ButtonAction.SUBMIT,
        binds: MutableMapping[str, BindCallback] = None,
        bind_enter: Bool = False,
        separate: Bool = False,
        **kwargs,
    ):
        if not binds:
            binds = {}
        if separate:
            self.separate = True
            binds.setdefault('<ButtonPress-1>', self.handle_press)
            binds.setdefault('<ButtonRelease-1>', self.handle_release)
        if shortcut:
            if not shortcut.startswith('<') or not shortcut.endswith('>'):
                raise ValueError(f'Invalid keyboard {shortcut=}')
            binds[shortcut] = self.handle_activated
        if bind_enter:
            self.bind_enter = True
            binds['<Return>'] = self.handle_activated
        super().__init__(binds=binds, justify_text=justify_text, **kwargs)
        self.text = text
        self.image = as_image(image)
        self.disabled = disabled
        self._focus = focus
        self.action = ButtonAction(action)
        self._last_press = 0
        self._last_release = 0
        self._last_activated = 0

    def _pack_size(self) -> XY:
        # Width is measured in pixels, but height is measured in characters
        # TODO: Width may not be correct yet
        try:
            width, height = self.size
        except TypeError:
            width, height = 0, 0
        if width and height:
            return width, height

        text, image = self.text, self.image
        if not text and not image:
            return width, height

        style = self.style
        if text and image:
            if not width:
                # width = int(ceil(image.width / style.char_width)) + len(text)
                width = style.char_width * len(text) + image.width
            if not height:
                height = int(ceil(image.height / style.char_height))
                # height = style.char_height + image.height
        elif text:
            if not width:
                # pass
                width = len(text) + 1
                # width = style.char_width * len(text)
            if not height:
                height = 1
                # height = style.char_height
        else:
            if not width:
                width = int(ceil(image.width / style.char_width))
                # width = image.width
            if not height:
                height = 1
                # height = image.height

        return width, height

    def pack_into(self, row: Row):
        # self.string_var = StringVar()
        # self.string_var.set(self._value)
        style = self.style
        width, height = self._pack_size()
        kwargs = {
            'width': width,
            'height': height,
            'font': style.font,
            'bd': style.border_width,
            'justify': self.justify_text.value,
        }
        if not self.separate:
            kwargs['command'] = self.handle_activated
        if self.text:
            kwargs['text'] = self.text
        if image := self.image:
            kwargs['image'] = image = PhotoImage(image)
            kwargs['compound'] = tkc.CENTER
            kwargs['highlightthickness'] = 0
        elif not self.pad or 0 in self.pad:
            kwargs['highlightthickness'] = 0
        if width:
            kwargs['wraplength'] = width * style.char_width
        if style.border_width == 0:
            kwargs['relief'] = tkc.FLAT  # May not work on mac

        style.update_kwargs(kwargs, STYLE_KEY_MAP, self.disabled)
        self.widget = button = _Button(row.frame, **kwargs)
        if image:
            button.image = image

        # button.pack(side=tkc.LEFT, expand=False, fill=tkc.NONE, **self.pad_kw)
        self.pack_widget(focus=self._focus, disabled=self.disabled)

    def _bind(self, event_pat: str, cb: BindCallback):
        super()._bind(event_pat, cb)
        if self.bind_enter and event_pat == '<Return>' and event_pat not in self.window._bound_for_events:
            self.window.bind(event_pat, cb)
            self.window._bound_for_events.add(event_pat)

    @property
    def value(self) -> bool:
        return bool(self._last_activated)

    def handle_press(self, event: Event):
        self._last_press = monotonic()
        # log.info(f'handle_press: {event=}')

    def handle_release(self, event: Event):
        self._last_release = monotonic()
        # log.info(f'handle_release: {event=}')
        self.handle_activated(event)

    def handle_activated(self, event: Event = None):
        self._last_activated = monotonic()
        log.info(f'handle_activated: {event=}')
        if self.action == ButtonAction.SUBMIT:
            self.window.interrupt()
        else:
            log.warning(f'No action configured for button={self}')
