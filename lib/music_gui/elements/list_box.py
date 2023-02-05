"""
Editable list box, primarily intended to be used for genres.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Collection, Callable

from ds_tools.caching.decorators import cached_property
from tk_gui.elements import Element, ListBox, Button
from tk_gui.elements.frame import InteractiveRowFrame
from tk_gui.popups import popup_get_text

if TYPE_CHECKING:
    from tkinter import Event

__all__ = ['EditableListBox']
log = logging.getLogger(__name__)


class EditableListBox(InteractiveRowFrame):
    def __init__(
        self,
        values: Collection[str],
        add_title: str,
        add_prompt: str,
        key: str = None,
        list_width: int = 30,
        val_type: Callable = None,
        **kwargs,
    ):
        kwargs.setdefault('pad', (0, 0))
        super().__init__(**kwargs)
        self.__key: str = key
        self._values = values
        self._list_width = list_width
        self.add_title = add_title
        self.add_prompt = add_prompt
        self._val_type = val_type

    @property
    def value(self):
        value = self.list_box.value
        if (val_type := self._val_type) is not None:
            return val_type(value)
        return value

    @cached_property
    def list_box(self) -> ListBox:
        values = self._values
        kwargs = {
            'size': (self._list_width, len(values)),
            'tooltip': 'Unselected items will not be saved',
            'pad': (4, 0),
            'border': 2,
        }
        return ListBox(values, default=values, disabled=self.disabled, scroll_y=False, key=self.__key, **kwargs)

    @cached_property
    def button(self) -> Button:
        if key := self.__key:
            key = f'add::{key}'
        return Button('Add...', key=key, pad=(0, 0), visible=not self.disabled, cb=self.add_value)

    def add_value(self, event: Event):
        if value := popup_get_text(self.add_prompt, self.add_title, bind_esc=True):
            self.list_box.append_choice(value, True)

    @property
    def elements(self) -> tuple[Element, ...]:
        return self.list_box, self.button

    def enable(self):
        if not self.disabled:
            return
        self.button.show()
        self.list_box.enable()
        self.disabled = False

    def disable(self):
        if self.disabled:
            return
        self.button.hide()
        self.list_box.disable()
        self.disabled = True
