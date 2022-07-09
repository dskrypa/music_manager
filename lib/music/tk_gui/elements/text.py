"""
Input GUI elements

:author: Doug Skrypa
"""

from __future__ import annotations

import logging
import tkinter.constants as tkc
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


"""
RELIEF_RAISED = 'raised'
RELIEF_SUNKEN = 'sunken'
RELIEF_FLAT = 'flat'
RELIEF_RIDGE = 'ridge'
RELIEF_GROOVE = 'groove'
RELIEF_SOLID = 'solid'
"""


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
        kwargs = {'textvariable': self.string_var, 'justify': self.justify_text.value}
        try:
            kwargs['width'], kwargs['height'] = self.size
        except TypeError:
            pass
        kwargs.update(self.style.get('fg', 'bg', 'font', 'relief', layer='text', border_width='bd'))  # noqa
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
        scroll_vertical: bool = True,
        scroll_horizontal: bool = False,
        auto_scroll: bool = False,
        rstrip: bool = True,
        justify_text: Union[str, Justify, None] = Justify.LEFT,
        **kwargs,
    ):
        super().__init__(justify_text=justify_text, **kwargs)
        self._value = str(value)
        self.scroll_vertical = scroll_vertical
        self.scroll_horizontal = scroll_horizontal
        self.auto_scroll = auto_scroll
        self.rstrip = rstrip

    def pack_into(self, row: Row):
        self.frame = frame = Frame(row.frame)

        # kwargs = {'justify': self.justify_text.value, 'highlightthickness': 0}
        kwargs = {'highlightthickness': 0}
        try:
            kwargs['width'], kwargs['height'] = self.size
        except TypeError:
            print('Bad multiline size')
            pass
        kwargs.update(self.style.get('fg', 'bg', 'font', 'relief', layer='text', border_width='bd'))  # noqa
        kwargs.setdefault('relief', 'sunken')
        if bg := kwargs.get('bg'):
            kwargs['selectforeground'] = bg
        if fg := kwargs.get('fg'):
            kwargs['selectbackground'] = fg
        if insert_bg := self.style.insert.bg.default:
            kwargs['insertbackground'] = insert_bg

        print(f'Initializing Text ele with {kwargs=}')
        self.widget = text = TkText(frame, **kwargs)
        if self.scroll_vertical:
            self._add_scroll_bar()
        if self.scroll_horizontal:
            text.config(wrap='none')
            self._add_scroll_bar(False)
        else:
            text.config(wrap='word')

        # if not element.no_scrollbar or element.HorizontalScroll:
        #     element.TKText.bind('<Enter>', lambda event, em=element: testMouseHook(em))
        #     element.TKText.bind('<Leave>', lambda event, em=element: testMouseUnhook(em))

        if value := self._value:
            text.insert(1.0, value)

        for pos in ('center', 'left', 'right'):
            text.tag_configure(pos, justify=pos)  # noqa

        if (justify := self.justify_text) != Justify.NONE:
            text.tag_add(justify.value, 1.0, 'end')

        self.pack_widget(widget=frame)
        self.pack_widget()
