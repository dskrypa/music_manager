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

from .element import Element

if TYPE_CHECKING:
    from pathlib import Path
    from ..pseudo_elements import Row

__all__ = ['Input']
log = logging.getLogger(__name__)


class Input(Element):
    widget: Entry
    string_var: Optional[StringVar] = None
    password_char: Optional[str] = None

    def __init__(
        self,
        value: Any = '',
        link: bool = None,
        path: Union[bool, str, Path] = None,
        password_char: str = None,
        justify_text: str = tkc.LEFT,
        disabled: bool = False,
        focus: bool = False,
        **kwargs
    ):
        super().__init__(**kwargs)
        self._value = str(value)
        self._valid = True
        self._link = link or link is None
        self._path = path
        if password_char:
            self.password_char = password_char
        self.disabled = disabled
        self._focus = focus
        self.justify_text = justify_text

    def get_selection(self):
        entry = self.widget
        selection = entry.selection_get()
        if not entry.selection_present():
            raise NotSelectionOwner
        return selection

    def pack_into(self, row: Row):
        self.string_var = StringVar()
        self.string_var.set(self._value)
        style = self.style
        self.widget = entry = Entry(
            row.frame,
            width=self.size[0],
            textvariable=self.string_var,
            bd=style.border_width,
            font=style.font,
            show=self.password_char,
            justify=self.justify_text,  # noqa
        )
        fg, bg = style.get_fg_bg('input', 'disabled' if self.disabled else 'default')
        kwargs = {'highlightthickness': 0}
        kwargs.update(
            (k, v) for k, v in zip(('fg', 'bg', 'insertbackground'), (fg, bg, style.insert_bg)) if v is not None
        )
        entry.configure(**kwargs)
        entry.pack(side=tkc.LEFT, expand=False, fill=tkc.NONE, **self.pad_kw)
        if not self._visible:
            entry.pack_forget()
        if self._focus:
            entry.focus_set()
        if self.disabled:
            entry['state'] = 'readonly'

        entry.bind('<FocusOut>', partial(_clear_selection, entry))  # Prevents ghost selections
        if self._link:
            entry.bind('<Control-Button-1>', self._open_link)
            if (value := self._value) and value.startswith(('http://', 'https://')):
                entry.configure(cursor='hand2')

    def _refresh_colors(self):
        fg, bg = self.style.get_fg_bg('input', 'default' if self._valid else 'invalid')
        self.widget.configure(**{'fg': fg, 'readonlybackground' if self.disabled else 'bg': bg})

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
        if self._valid != valid:
            self._valid = valid
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
