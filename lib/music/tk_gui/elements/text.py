"""
Text GUI elements

:author: Doug Skrypa
"""

from __future__ import annotations

import logging
import tkinter.constants as tkc
import webbrowser
from contextlib import contextmanager
from functools import cached_property
from tkinter import TclError, StringVar, Label, Event, Entry
from typing import TYPE_CHECKING, Optional, Union, Any

from ..enums import Justify, Anchor
from ..pseudo_elements.scroll import ScrollableText
from ..style import Style, Font
from ..utils import max_line_len
from .element import Element

if TYPE_CHECKING:
    # from pathlib import Path
    from ..pseudo_elements import Row
    from ..typing import Bool

__all__ = ['Text', 'Link', 'Multiline', 'GuiTextHandler', 'gui_log_handler']
log = logging.getLogger(__name__)

LINK_BIND_DEFAULT = '<Control-ButtonRelease-1>'


class Text(Element):
    widget: Union[Label, Entry]
    string_var: Optional[StringVar] = None

    def __init__(
        self,
        value: Any = '',
        link: Union[bool, str] = None,
        # path: Union[bool, str, Path] = None,
        *,
        justify: Union[str, Justify] = None,
        anchor: Union[str, Anchor] = None,
        link_bind: str = LINK_BIND_DEFAULT,
        selectable: Bool = True,
        **kwargs,
    ):
        self._tooltip_text = kwargs.pop('tooltip', None)
        if justify is anchor is None:
            justify = Justify.LEFT
            if not selectable:
                anchor = Justify.LEFT.as_anchor()
        super().__init__(justify_text=justify, anchor=anchor, **kwargs)
        self._link_bind = link_bind
        self._value = str(value)
        self._link = link or link is None
        self._selectable = selectable
        # self._path = path

    @property
    def pad_kw(self) -> dict[str, int]:
        try:
            x, y = self.pad
        except TypeError:
            if self._selectable:
                x, y = 5, 3
            else:
                x, y = 0, 3

        return {'padx': x, 'pady': y}

    @property
    def style_config(self) -> dict[str, Any]:
        return {
            **self.style.get_map('text', bd='border_width', fg='fg', bg='bg', font='font', relief='relief'),
            **self._style_config,
        }

    def pack_into(self, row: Row, column: int):
        self.string_var = StringVar()
        self.string_var.set(self._value)

        if self._selectable:
            self._pack_entry(row)
        else:
            self._pack_label(row)

        self.pack_widget()
        if self.url:
            self._enable_link()

    def _pack_label(self, row: Row):
        kwargs = {
            'textvariable': self.string_var,
            'justify': self.justify_text.value,
            'wraplength': 0,
            **self.style_config,
        }
        try:
            kwargs['width'], kwargs['height'] = self.size
        except TypeError:
            pass
        self.widget = label = Label(row.frame, **kwargs)
        if kwargs.get('height', 1) != 1:
            wrap_len = label.winfo_reqwidth()  # width in pixels
            label.configure(wraplength=wrap_len)

    def _pack_entry(self, row: Row):
        kwargs = {
            'highlightthickness': 0,
            'textvariable': self.string_var,
            'justify': self.justify_text.value,
            'state': 'readonly',
            **self.style.get_map('text', readonlybackground='bg'),
            **self.style_config,
        }
        kwargs.setdefault('relief', 'flat')
        try:
            kwargs['width'] = self.size[0]
        except TypeError:
            pass
        self.widget = Entry(row.frame, **kwargs)

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
        widget = self.widget
        widget.bind(self._link_bind, self._open_link)
        widget.configure(cursor='hand2', fg=self.style.link.fg.default)

    def _disable_link(self):
        widget = self.widget
        widget.unbind(self._link_bind)
        widget.configure(cursor='', fg=self.style.text.fg.default)

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
        auto_scroll: bool = False,
        rstrip: bool = False,
        justify_text: Union[str, Justify, None] = Justify.LEFT,
        **kwargs,
    ):
        super().__init__(justify_text=justify_text, **kwargs)
        self._value = str(value)
        self.scroll_y = scroll_y
        self.scroll_x = scroll_x
        self.auto_scroll = auto_scroll
        self.rstrip = rstrip

    @property
    def style_config(self) -> dict[str, Any]:
        style = self.style
        config: dict[str, Any] = {
            'highlightthickness': 0,
            **style.get_map('text', attrs=('fg', 'bg', 'font', 'relief'), bd='border_width'),  # noqa
            **style.get_map('selected', selectforeground='fg', selectbackground='bg'),
            **style.get_map('insert', insertbackground='bg'),
            **self._style_config,
        }
        config.setdefault('relief', 'sunken')
        return config

    def pack_into(self, row: Row, column: int):
        kwargs = self.style_config
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

        """
        maxundo:
        spacing1:
        spacing2:
        spacing3:
        tabs:
        undo:
        wrap:
        """
        self.widget = scroll_text = ScrollableText(row.frame, self.scroll_y, self.scroll_x, self.style, **kwargs)
        text = scroll_text.inner_widget
        if value:
            text.insert(1.0, value)
        if (justify := self.justify_text) != Justify.NONE:
            text.tag_add(justify.value, 1.0, 'end')
        for pos in ('center', 'left', 'right'):
            text.tag_configure(pos, justify=pos)  # noqa

        self.pack_widget()

    def clear(self):
        self.widget.inner_widget.delete('1.0', tkc.END)

    def write(self, text: str, *, fg: str = None, bg: str = None, font: Font = None, append: Bool = False):
        widget = self.widget.inner_widget
        # TODO: Handle justify
        if fg or bg or font:
            style = Style(parent=self.style, text_fg=fg, text_bg=bg, text_font=font)
            tag = f'{self.__class__.__name__}({fg},{bg},{font})'
            widget.tag_configure(tag, **style.get_map('text', background='bg', foreground='fg', font='font'))
            args = ((None, tag),)
        else:
            args = ()

        if not append:
            self.clear()

        if self.rstrip:
            text = '\n'.join(line.rstrip() for line in text.splitlines())

        widget.insert(tkc.END, text, *args)
        if self.auto_scroll:
            widget.see(tkc.END)


# region Log to Element Handling


class GuiTextHandler(logging.Handler):
    def __init__(self, element: Multiline, level: int = logging.NOTSET):
        super().__init__(level)
        self.element = element

    def emit(self, record):
        try:
            msg = self.format(record)
            self.element.write(msg + '\n', append=True)
        except RecursionError:  # See issue 36272
            raise
        except TclError:
            pass  # The element was most likely destroyed
        except Exception:  # noqa
            self.handleError(record)


@contextmanager
def gui_log_handler(
    element: Multiline,
    logger_name: str = None,
    level: int = logging.DEBUG,
    detail: bool = False,
    logger: logging.Logger = None,
):
    from ds_tools.logging import DatetimeFormatter, ENTRY_FMT_DETAILED

    handler = GuiTextHandler(element, level)
    if detail:
        handler.setFormatter(DatetimeFormatter(ENTRY_FMT_DETAILED, '%Y-%m-%d %H:%M:%S %Z'))

    loggers = [logging.getLogger(logger_name), logger] if logger else [logging.getLogger(logger_name)]
    for logger in loggers:
        logger.addHandler(handler)
    try:
        yield handler
    finally:
        for logger in loggers:
            logger.removeHandler(handler)


# endregion
