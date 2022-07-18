"""
Text GUI elements

:author: Doug Skrypa
"""

from __future__ import annotations

import logging
import webbrowser
from functools import cached_property
from tkinter import StringVar, Label, Event
from typing import TYPE_CHECKING, Optional, Union, Any

from ..enums import Justify
from ..pseudo_elements.scroll import ScrollableText
from ..utils import max_line_len
from .element import Element

if TYPE_CHECKING:
    # from pathlib import Path
    from ..pseudo_elements import Row

__all__ = ['Text', 'Link', 'Multiline']
log = logging.getLogger(__name__)

LINK_BIND_DEFAULT = '<Control-ButtonRelease-1>'


class Text(Element):
    widget: Label
    string_var: Optional[StringVar] = None

    def __init__(
        self,
        value: Any = '',
        link: Union[bool, str] = None,
        # path: Union[bool, str, Path] = None,
        justify_text: Union[str, Justify, None] = Justify.LEFT,
        *,
        link_bind: str = LINK_BIND_DEFAULT,
        **kwargs,
    ):
        self._tooltip_text = kwargs.pop('tooltip', None)
        super().__init__(justify_text=justify_text, **kwargs)
        self._link_bind = link_bind
        self._value = str(value)
        self._link = link or link is None
        # self._path = path

    def pack_into(self, row: Row, column: int):
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
        if self.url:
            self._enable_link()

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
    def tooltip_text(self) -> str:
        tooltip = self._tooltip_text
        if not (url := self.url):
            return tooltip

        link_text = 'link' if self._link is True else url
        prefix = f'{tooltip}; open' if tooltip else 'Open'
        suffix = ' with ctrl + click' if self._link_bind == LINK_BIND_DEFAULT else ''
        return f'{prefix} {link_text} in a browser{suffix}'

    # region Link Handling

    @cached_property
    def url(self) -> Optional[str]:
        if link := self._link:
            url = link if isinstance(link, str) else self._value
            return url if url.startswith(('http://', 'https://')) else None
        return None

    def update_link(self, link: Union[bool, str]):
        old = self._link
        self._link = link
        self.clear_cached_properties('url', 'tooltip_text')
        self.add_tooltip(self.tooltip_text)
        if link and not old:
            self._enable_link()
        elif old and not link:
            self._disable_link()

    def _enable_link(self):
        label = self.widget
        label.bind(self._link_bind, self._open_link)
        label.configure(cursor='hand2', fg=self.style.link.fg.default)

    def _disable_link(self):
        label = self.widget
        label.unbind(self._link_bind)
        label.configure(cursor='', fg=self.style.text.fg.default)

    def _open_link(self, event: Event = None):
        if not (url := self.url):
            return
        width, height = self.size_and_pos[0]
        if 0 <= event.x <= width and 0 <= event.y <= height:
            webbrowser.open(url)

    # endregion


class Link(Text):
    def __init__(self, value: Any = '', link: Union[bool, str] = True, link_bind: str = '<ButtonRelease-1>', **kwargs):
        super().__init__(value, link=link, link_bind=link_bind, **kwargs)


class Multiline(Element):
    widget: ScrollableText

    def __init__(
        self,
        value: Any = '',
        *,
        scroll_y: bool = True,
        scroll_x: bool = False,
        # auto_scroll: bool = False,  # TODO
        rstrip: bool = True,
        justify_text: Union[str, Justify, None] = Justify.LEFT,
        **kwargs,
    ):
        super().__init__(justify_text=justify_text, **kwargs)
        self._value = str(value)
        self.scroll_y = scroll_y
        self.scroll_x = scroll_x
        # self.auto_scroll = auto_scroll
        self.rstrip = rstrip

    def pack_into(self, row: Row, column: int):
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

        value = self._value
        if self.rstrip:
            lines = [line.rstrip() for line in value.splitlines()]
            value = '\n'.join(lines)
            if 'width' not in kwargs:
                kwargs['width'] = max_line_len(lines)
        elif 'width' not in kwargs:
            kwargs['width'] = max_line_len(value.splitlines())

        self.widget = scroll_text = ScrollableText(row.frame, self.scroll_y, self.scroll_x, style, **kwargs)
        text = scroll_text.inner_widget
        if value:
            text.insert(1.0, value)
        if (justify := self.justify_text) != Justify.NONE:
            text.tag_add(justify.value, 1.0, 'end')
        for pos in ('center', 'left', 'right'):
            text.tag_configure(pos, justify=pos)  # noqa

        self.pack_widget()
