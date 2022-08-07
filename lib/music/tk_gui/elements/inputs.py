"""
Input GUI elements

:author: Doug Skrypa
"""

from __future__ import annotations

import logging
import tkinter.constants as tkc
import webbrowser
from functools import partial
from tkinter import TclError, Entry, StringVar
from typing import TYPE_CHECKING, Optional, Union, Any

from ..enums import Justify
from .element import Interactive

if TYPE_CHECKING:
    from pathlib import Path
    from ..pseudo_elements import Row
    from ..typing import Bool, BindTarget

__all__ = ['Input']
log = logging.getLogger(__name__)


class Input(Interactive):
    widget: Entry
    string_var: Optional[StringVar] = None
    password_char: Optional[str] = None

    def __init__(
        self,
        value: Any = '',
        *,
        link: bool = None,
        path: Union[bool, str, Path] = None,
        password_char: str = None,
        justify_text: Union[str, Justify, None] = Justify.LEFT,
        callback: BindTarget = None,
        **kwargs
    ):
        super().__init__(justify_text=justify_text, **kwargs)
        self._value = str(value)
        self._link = link or link is None
        self._path = path
        self._callback = callback
        if password_char:
            self.password_char = password_char

    def get_selection(self):
        entry = self.widget
        selection = entry.selection_get()
        if not entry.selection_present():
            raise NotSelectionOwner
        return selection

    @property
    def value(self) -> str:
        return self.string_var.get()

    @property
    def style_config(self) -> dict[str, Any]:
        style, state = self.style, self.style_state
        return {
            'highlightthickness': 0,
            **style.get_map('input', state, bd='border_width', fg='fg', bg='bg', font='font', relief='relief'),
            **style.get_map('input', 'disabled', readonlybackground='bg'),
            **style.get_map('insert', state, insertbackground='bg'),
            **self._style_config,
        }

    def pack_into(self, row: Row, column: int):
        self.string_var = StringVar()
        self.string_var.set(self._value)
        kwargs = {
            'textvariable': self.string_var,
            'show': self.password_char,
            'justify': self.justify_text.value,
            'takefocus': int(self.allow_focus),
            **self.style_config,
        }
        try:
            kwargs['width'] = self.size[0]
        except TypeError:
            pass

        self.widget = entry = Entry(row.frame, **kwargs)
        self.pack_widget()

        entry.bind('<FocusOut>', partial(_clear_selection, entry))  # Prevents ghost selections
        if self._link:
            entry.bind('<Control-Button-1>', self._open_link)
            if (value := self._value) and value.startswith(('http://', 'https://')):
                entry.configure(cursor='hand2')
        if (callback := self._callback) is not None:
            entry.bind('<Key>', self.normalize_callback(callback))

    def update(self, value: Any = None, disabled: Bool = None, password_char: str = None):
        if disabled is not None:
            self._update_state(disabled)
        if value is not None:
            self._value = str(value)
            self.string_var.set(self._value)
            self.widget.icursor(tkc.END)
        if password_char is not None:
            self.widget.configure(show=password_char)
            self.password_char = password_char

    # region Update State

    def disable(self):
        if self.disabled:
            return
        self._update_state(True)

    def enable(self):
        if not self.disabled:
            return
        self._update_state(False)

    def validated(self, valid: bool):
        if self.valid != valid:
            self.valid = valid
            self._refresh_colors()

    def _update_state(self, disabled: bool):
        self.disabled = disabled
        self.widget['state'] = 'readonly' if disabled else 'normal'
        self._refresh_colors()

    def _refresh_colors(self):
        bg_key = 'readonlybackground' if self.disabled else 'bg'
        kwargs = self.style.get_map('input', self.style_state, fg='fg', **{bg_key: 'bg'})
        log.debug(f'Refreshing colors for {self} with {self.style_state=}: {kwargs}')
        self.widget.configure(**kwargs)

    # endregion

    def handle_right_click(self, event):
        # TODO: Replace with new right-click menu/handling
        if (menu := self.right_click_menu) is not None:
            try:
                kwargs = {'selected': self.get_selection()}
            except (TclError, NotSelectionOwner):
                kwargs = {}
            menu.show(event, self.widget.master, **kwargs)  # noqa

    def _open_link(self, event):
        if (value := self.value) and value.startswith(('http://', 'https://')):
            webbrowser.open(value)


class NotSelectionOwner(Exception):
    pass


def _clear_selection(entry, event):
    entry.selection_clear()
