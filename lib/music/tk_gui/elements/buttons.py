"""
Tkinter GUI button elements

:author: Doug Skrypa
"""

from __future__ import annotations

import logging
import tkinter.constants as tkc
from enum import Enum
from math import ceil
from tkinter import TclError, Event, StringVar, Button as _Button
from typing import TYPE_CHECKING, Union, MutableMapping

from PIL.ImageTk import PhotoImage

from ds_tools.images.utils import ImageType, as_image

from .element import Element

if TYPE_CHECKING:
    from ..pseudo_elements import Row
    from ..utils import XY, BindCallback

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

    def __init__(
        self,
        text: str = '',
        image: ImageType = None,
        *,
        disabled: bool = False,
        focus: bool = False,
        shortcut: str = None,
        action: Union[ButtonAction, str] = ButtonAction.SUBMIT,
        binds: MutableMapping[str, BindCallback] = None,
        **kwargs,
    ):
        if not binds:
            binds = {}
        binds.setdefault('<ButtonPress-1>', self.handle_press)
        binds.setdefault('<ButtonRelease-1>', self.handle_release)
        if shortcut:
            if not shortcut.startswith('<') or not shortcut.endswith('>'):
                raise ValueError(f'Invalid keyboard {shortcut=}')
            binds[shortcut] = self.handle_activated
        super().__init__(binds=binds, **kwargs)
        self.text = text
        self.image = as_image(image)
        self.disabled = disabled
        self._focus = focus
        self._action = ButtonAction(action)

    def _pack_size(self) -> XY:
        # Width is measured in pixels, but height is measured in characters
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
                width = style.char_width * len(text) + image.width
            if not height:
                height = int(ceil(image.height / style.char_height))
                # height = style.char_height + image.height
        elif text:
            if not width:
                width = style.char_width * len(text)
            if not height:
                height = 1
                # height = style.char_height
        else:
            if not width:
                width = image.width
            if not height:
                height = 1
                # height = image.height

        return width, height

    def pack_into(self, row: Row):
        # self.string_var = StringVar()
        # self.string_var.set(self._value)
        style = self.style
        width, height = self._pack_size()
        kwargs = {'width': width, 'height': height, 'font': style.font, 'bd': style.border_width, 'justify': tkc.CENTER}
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

        state = 'disabled' if self.disabled else 'default'
        for attr, key in STYLE_KEY_MAP.items():
            if value := getattr(style, attr)[state]:
                kwargs[key] = value

        self.widget = button = _Button(row.frame, **kwargs)
        if image:
            button.image = image
        button.pack(side=tkc.LEFT, expand=False, fill=tkc.NONE, **self.pad_kw)
        if not self._visible:
            button.pack_forget()
        if self._focus:
            button.focus_set()
        if self.disabled:
            button['state'] = 'readonly'

    def handle_press(self, event: Event):
        log.info(f'handle_press: {event=}')

    def handle_release(self, event: Event):
        log.info(f'handle_release: {event=}')

    def handle_activated(self, event: Event):
        log.info(f'handle_activated: {event=}')
