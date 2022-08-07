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
from typing import TYPE_CHECKING, Union, Optional, Any, MutableMapping

from PIL.ImageTk import PhotoImage

from ds_tools.images.utils import ImageType, as_image, scale_image

from ..enums import Justify
from .element import Interactive

if TYPE_CHECKING:
    from PIL.Image import Image as PILImage
    from ..pseudo_elements import Row
    from ..typing import XY, BindCallback, Bool

__all__ = ['Button', 'OK', 'Cancel', 'Yes', 'No', 'Submit']
log = logging.getLogger(__name__)


class ButtonAction(Enum):
    SUBMIT = 'submit'

    @classmethod
    def _missing_(cls, value: str):
        try:
            return cls[value.upper()]
        except KeyError:
            return None


class Button(Interactive):
    widget: _Button
    separate: bool = False
    bind_enter: bool = False

    def __init__(
        self,
        text: str = '',
        image: ImageType = None,
        *,
        shortcut: str = None,
        justify_text: Union[str, Justify, None] = Justify.CENTER,
        action: Union[ButtonAction, str] = ButtonAction.SUBMIT,
        binds: MutableMapping[str, BindCallback] = None,
        bind_enter: Bool = False,
        separate: Bool = False,
        focus: Bool = None,
        **kwargs,
    ):
        if not binds:
            binds = {}
        if separate:
            self.separate = True
            binds.setdefault('<ButtonPress-1>', self.handle_press)
            binds.setdefault('<ButtonRelease-1>', self.handle_release)
        if shortcut:  # TODO: This does not activate (without focus?)
            if len(shortcut) == 1:
                shortcut = f'<{shortcut}>'
            if not shortcut.startswith('<') or not shortcut.endswith('>'):
                raise ValueError(f'Invalid keyboard {shortcut=}')
            binds[shortcut] = self.handle_activated
        if bind_enter:
            self.bind_enter = True
            binds['<Return>'] = self.handle_activated
        if focus is None:
            focus = bind_enter
        super().__init__(binds=binds, justify_text=justify_text, focus=focus, **kwargs)
        self.text = text
        self.image = image
        self.action = ButtonAction(action)
        self._last_press = 0
        self._last_release = 0
        self._last_activated = 0

    @property
    def image(self) -> Optional[PILImage]:
        return self._image

    @image.setter
    def image(self, value: ImageType):
        self._image = image = as_image(value)
        if not image or not self.size:
            return

        iw, ih = image.size
        width, height = self.size
        if ih > height or iw > width:
            self._image = scale_image(image, width - 1, height - 1)
        # if text := self.text:
        #     style = self.style
        #     state = self.style_state
        #     tw, th = style.text_size(text, layer='button', state=state)
        #     if th <= height and tw < width:

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
                # width = int(ceil(image.width / style.char_width())) + len(text)
                width = style.char_width('button') * len(text) + image.width
            if not height:
                height = int(ceil(image.height / style.char_height('button')))
                # height = style.char_height() + image.height
        elif text:
            if not width:
                # pass
                width = len(text) + 1
                # width = style.char_width() * len(text)
            if not height:
                height = 1
                # height = style.char_height()
        else:
            if not width:
                # width = int(ceil(image.width / style.char_width()))
                width = image.width
            if not height:
                # height = 1
                height = image.height

        return width, height

    @property
    def style_config(self) -> dict[str, Any]:
        style, state = self.style, self.style_state
        config = {
            **style.get_map('button', state, bd='border_width', font='font', foreground='fg', background='bg'),
            **style.get_map('button', 'active', activeforeground='fg', activebackground='bg'),
            **style.get_map('button', 'highlight', highlightcolor='fg', highlightbackground='bg'),
            **self._style_config,
        }
        if style.button.border_width[state] == 0:
            config['relief'] = tkc.FLAT  # May not work on mac

        return config

    def pack_into(self, row: Row, column: int):
        # self.string_var = StringVar()
        # self.string_var.set(self._value)
        width, height = self._pack_size()
        kwargs = {
            'width': width,
            'height': height,
            'justify': self.justify_text.value,
            'takefocus': int(self.allow_focus),
            **self.style_config,
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
            kwargs['wraplength'] = width * self.style.char_width('button', self.style_state)

        self.widget = button = _Button(row.frame, **kwargs)
        if image:
            button.image = image

        self.pack_widget()

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
        log.debug(f'handle_activated: {event=}')
        if self.action == ButtonAction.SUBMIT:
            self.window.interrupt(event, self)
        else:
            log.warning(f'No action configured for button={self}')


def OK(text: str = 'OK', bind_enter: Bool = True, **kwargs) -> Button:
    return Button(text, bind_enter=bind_enter, **kwargs)


def Cancel(text: str = 'Cancel', **kwargs) -> Button:
    return Button(text, **kwargs)


def Yes(text: str = 'Yes', bind_enter: Bool = True, **kwargs) -> Button:
    return Button(text, bind_enter=bind_enter, **kwargs)


def No(text: str = 'No', **kwargs) -> Button:
    return Button(text, **kwargs)


def Submit(text: str = 'Submit', bind_enter: Bool = True, **kwargs) -> Button:
    return Button(text, bind_enter=bind_enter, **kwargs)
