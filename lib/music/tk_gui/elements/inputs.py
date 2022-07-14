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

__all__ = ['Input']
log = logging.getLogger(__name__)


class Input(Interactive):
    widget: Entry
    string_var: Optional[StringVar] = None
    password_char: Optional[str] = None

    def __init__(
        self,
        value: Any = '',
        link: bool = None,
        path: Union[bool, str, Path] = None,
        password_char: str = None,
        justify_text: Union[str, Justify, None] = Justify.LEFT,
        **kwargs
    ):
        super().__init__(justify_text=justify_text, **kwargs)
        self._value = str(value)
        self._link = link or link is None
        self._path = path
        if password_char:
            self.password_char = password_char

    def get_selection(self):
        entry = self.widget
        selection = entry.selection_get()
        if not entry.selection_present():
            raise NotSelectionOwner
        return selection

    def pack_into(self, row: Row, column: int):
        self.string_var = StringVar()
        self.string_var.set(self._value)
        style = self.style
        state = self.style_state
        kwargs = {
            'highlightthickness': 0,
            'textvariable': self.string_var,
            'show': self.password_char,
            'justify': self.justify_text.value,
            **style.get_map('input', state, bd='border_width', fg='fg', bg='bg', font='font'),
            **style.get_map('insert', state, insertbackground='bg'),
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

    def _refresh_colors(self):
        bg_key = 'readonlybackground' if self.disabled else 'bg'
        kwargs = self.style.get_map('input', self.style_state, fg='fg', **{bg_key: 'bg'})
        self.widget.configure(**kwargs)

    def update(self, value=None, disabled: bool = None, password_char: str = None):
        entry = self.widget
        if disabled is not None:
            if disabled:
                entry['state'] = 'readonly'
            elif disabled is False:
                entry['state'] = 'normal'
            self.disabled = disabled
            self._refresh_colors()
        if value is not None:
            self._value = str(value)
            self.string_var.set(self._value)
            entry.icursor(tkc.END)
        if password_char is not None:
            entry.configure(show=password_char)
            self.password_char = password_char

    @property
    def value(self):
        return self.string_var.get()

    def validated(self, valid: bool):
        if self.valid != valid:
            self.valid = valid
            self._refresh_colors()

    def handle_right_click(self, event):
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
