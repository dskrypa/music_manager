"""
Input GUI elements

:author: Doug Skrypa
"""

from __future__ import annotations

import logging
import webbrowser
from functools import cached_property
from tkinter import StringVar, Label, Event, Frame, Text as TkText
from typing import TYPE_CHECKING, Optional, Union, Any

from .element import Element, ScrollableMixin
from ..utils import Justify

if TYPE_CHECKING:
    from pathlib import Path
    from ..pseudo_elements import Row

__all__ = ['Text', 'Multiline']
log = logging.getLogger(__name__)


class Text(Element):
    widget: Label
    string_var: Optional[StringVar] = None

    def __init__(
        self,
        value: Any = '',
        link: Union[bool, str] = None,
        path: Union[bool, str, Path] = None,
        justify_text: Union[str, Justify, None] = Justify.LEFT,
        **kwargs
    ):
        self._tooltip_text = kwargs.pop('tooltip', None)
        super().__init__(justify_text=justify_text, **kwargs)
        self._value = str(value)
        self._link = link or link is None
        self._path = path

    def pack_into(self, row: Row):
        self.string_var = StringVar()
        self.string_var.set(self._value)
        style = self.style
        kwargs = {
            'textvariable': self.string_var,
            'justify': self.justify_text.value,
            **style.get_map('text', bd='border_width', fg='fg', bg='bg', font='font', relief='relief'),
        }
        try:
            kwargs['width'], kwargs['height'] = self.size
        except TypeError:
            pass
        self.widget = label = Label(row.frame, **kwargs)
        # if kwargs.get('height') != 1:
        #     wrap_len = label.winfo_reqwidth()  # width in pixels
        #     label.configure(wraplength=wrap_len)
        self.pack_widget()
        if self._link:
            self._enable_link()

    def _enable_link(self):
        label = self.widget
        label.bind('<Control-Button-1>', self._open_link)
        if (value := self._value) and value.startswith(('http://', 'https://')):
            label.configure(cursor='hand2')

    def _disable_link(self):
        label = self.widget
        label.unbind('<Control-Button-1>')
        label.configure(cursor='')

    def update(self, value: Any = None, link: Union[bool, str] = None):
        if value is not None:
            self._value = str(value)
            self.string_var.set(self._value)
        if link is not None:
            self.update_link(link)

    @property
    def value(self):
        return self.string_var.get()

    @cached_property
    def url(self) -> Optional[str]:
        if link := self._link:
            url = link if isinstance(link, str) else self._value
            return url if url.startswith(('http://', 'https://')) else None
        return None

    @cached_property
    def tooltip_text(self) -> str:
        if url := self.url:
            link_text = 'link' if self._link is True else url
            if tooltip := self._tooltip_text:
                return f'{tooltip}; open {link_text} in browser with ctrl + click'
            return f'Open {link_text} in browser with ctrl + click'
        return self._tooltip_text

    def _open_link(self, event: Event = None):
        if url := self.url:
            webbrowser.open(url)

    def update_link(self, link: Union[bool, str]):
        old = self._link
        self._link = link
        self.clear_cached_properties('url', 'tooltip_text')
        self.add_tooltip(self.tooltip_text)
        if link and not old:
            self._enable_link()
        elif old and not link:
            self._disable_link()


class Multiline(Element, ScrollableMixin):
    frame: Frame
    widget: TkText

    def __init__(
        self,
        value: Any = '',
        *,
        scroll_y: bool = True,
        scroll_x: bool = False,
        auto_scroll: bool = False,
        rstrip: bool = True,
        justify_text: Union[str, Justify, None] = Justify.LEFT,
        **kwargs,
    ):
        super().__init__(justify_text=justify_text, **kwargs)
        self._value = str(value)
        self.scroll_y = scroll_y
        self.scroll_x = scroll_x
        self.auto_scroll = auto_scroll
        self.rstrip = rstrip

    def pack_into(self, row: Row):
        self.frame = frame = Frame(row.frame)
        style = self.style
        kwargs = {
            'highlightthickness': 0,
            **style.get_map('text', attrs=('fg', 'bg', 'font', 'relief'), bd='border_width'),  # noqa
            **style.get_map('selected', selectforeground='fg', selectbackground='bg'),
            **style.get_map('insert', insertbackground='bg'),
        }
        kwargs.setdefault('relief', 'sunken')  # noqa
        try:
            kwargs['width'], kwargs['height'] = self.size
        except TypeError:
            pass

        self.widget = text = TkText(frame, **kwargs)
        if self.scroll_y:
            self.add_scroll_bar()
        if self.scroll_x:
            text.config(wrap='none')
            self.add_scroll_bar(False)
        else:
            text.config(wrap='word')

        if value := self._value:
            text.insert(1.0, value)

        for pos in ('center', 'left', 'right'):
            text.tag_configure(pos, justify=pos)  # noqa

        if (justify := self.justify_text) != Justify.NONE:
            text.tag_add(justify.value, 1.0, 'end')

        self.pack_widget(widget=frame)
        self.pack_widget()
