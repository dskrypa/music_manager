"""
Text GUI elements

:author: Doug Skrypa
"""

from __future__ import annotations

import logging
import tkinter.constants as tkc
import webbrowser
from abc import ABC, abstractmethod
from contextlib import contextmanager
from functools import cached_property, partial
from tkinter import TclError, StringVar, Label, Event, Entry, BaseWidget
from typing import TYPE_CHECKING, Optional, Union, Any

from ..constants import LEFT_CLICK, CTRL_LEFT_CLICK
from ..enums import Justify, Anchor
from ..pseudo_elements.scroll import ScrollableText
from ..style import Style, Font
from ..utils import max_line_len
from .element import Element, Interactive

if TYPE_CHECKING:
    from ..pseudo_elements import Row
    from ..typing import Bool, XY, BindTarget

__all__ = ['Text', 'Link', 'Input', 'Multiline', 'GuiTextHandler', 'gui_log_handler']
log = logging.getLogger(__name__)

_Link = Union[bool, str, 'BindTarget', None]

# region Link Targets


class LinkTarget(ABC):
    __slots__ = ('bind', '_tooltip')

    def __init__(self, bind: str, tooltip: str = None):
        self.bind = bind
        self._tooltip = tooltip

    @property
    def tooltip(self) -> Optional[str]:
        return self._tooltip

    @abstractmethod
    def open(self, event: Event):
        raise NotImplementedError

    @classmethod
    def new(cls, value: _Link, bind: str = None, tooltip: str = None, text: str = None) -> Optional[LinkTarget]:
        if not value:
            return None
        elif isinstance(value, LinkTarget):
            return value
        elif value is True:
            value = text

        if isinstance(value, str):
            if value.startswith(('http://', 'https://')):
                return UrlLink(value, bind, tooltip, url_in_tooltip=value != text)
            else:
                log.debug(f'Ignoring invalid url={value!r}')
                return None
        else:
            return CallbackLink(value, bind, tooltip)


class UrlLink(LinkTarget):
    __slots__ = ('url', 'url_in_tooltip')

    def __init__(self, url: str = None, bind: str = None, tooltip: str = None, url_in_tooltip: bool = False):
        super().__init__(CTRL_LEFT_CLICK if not bind and url else bind, tooltip)
        self.url = url
        self.url_in_tooltip = url_in_tooltip

    @property
    def tooltip(self) -> str:
        tooltip = self._tooltip
        if not (url := self.url):
            return tooltip

        link_text = url if self.url_in_tooltip else 'link'
        prefix = f'{tooltip}; open' if tooltip else 'Open'
        suffix = ' with ctrl + click' if self.bind == CTRL_LEFT_CLICK else ''
        return f'{prefix} {link_text} in a browser{suffix}'

    def open(self, event: Event):
        if url := self.url:
            webbrowser.open(url)


class CallbackLink(LinkTarget):
    __slots__ = ('callback',)

    def __init__(self, callback: BindTarget, bind: str = None, tooltip: str = None):
        super().__init__(bind or LEFT_CLICK, tooltip)
        self.callback = callback

    def open(self, event: Event):
        self.callback(event)


# endregion


class Text(Element):
    __link: Optional[LinkTarget] = None
    widget: Union[Label, Entry]
    string_var: Optional[StringVar] = None

    def __init__(
        self,
        value: Any = '',
        link: Union[bool, str, BindTarget] = None,
        *,
        justify: Union[str, Justify] = None,
        anchor: Union[str, Anchor] = None,
        link_bind: str = None,
        selectable: Bool = True,
        auto_size: Bool = True,
        **kwargs,
    ):
        self._tooltip_text = kwargs.pop('tooltip', None)
        if justify is anchor is None:
            justify = Justify.LEFT
            if not selectable:
                anchor = Justify.LEFT.as_anchor()
        super().__init__(justify_text=justify, anchor=anchor, **kwargs)
        self._value = str(value)
        self.link = (link_bind, link)
        self._selectable = selectable
        self._auto_size = auto_size

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

    def _init_size(self, font: Font) -> Optional[XY]:
        try:
            width, size = self.size
        except TypeError:
            pass
        else:
            return width, size
        if not self._auto_size or not self._value:
            return None
        lines = self._value.splitlines()
        width = max(map(len, lines))
        height = len(lines)
        if font and 'bold' in font:
            width += 1
        return width, height

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
        if self.__link:
            self._enable_link()

    def _pack_label(self, row: Row):
        kwargs = {
            'textvariable': self.string_var,
            'justify': self.justify_text.value,
            'wraplength': 0,
            'takefocus': int(self.allow_focus),
            **self.style_config,
        }
        try:
            kwargs['width'], kwargs['height'] = self._init_size(kwargs.get('font'))
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
            'takefocus': int(self.allow_focus),
            **self.style.get_map('text', readonlybackground='bg'),
            **self.style_config,
        }
        kwargs.setdefault('relief', 'flat')
        try:
            kwargs['width'] = self._init_size(kwargs.get('font'))[0]
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

    @property
    def tooltip_text(self) -> str:
        try:
            return self.__link.tooltip
        except AttributeError:
            return self._tooltip_text

    def should_ignore(self, event: Event) -> bool:
        """Return True if the event ended with the cursor outside this element, False otherwise"""
        width, height = self.size_and_pos[0]
        return not (0 <= event.x <= width and 0 <= event.y <= height)

    # region Link Handling

    @property
    def link(self) -> Optional[LinkTarget]:
        return self.__link

    @link.setter
    def link(self, value: Union[LinkTarget, _Link, tuple[Optional[str], _Link]]):
        if isinstance(value, LinkTarget):
            self.__link = value
            return
        elif isinstance(value, tuple):
            bind, value = value
        else:
            bind = getattr(self.__link, 'bind', None)

        self.__link = LinkTarget.new(value, bind, self._tooltip_text, self._value)

    def update_link(self, link: Union[bool, str, BindTarget]):
        old = self.__link
        self.__link = new = LinkTarget.new(link, getattr(old, 'bind', None), self._tooltip_text, self._value)
        self.add_tooltip(new.tooltip if new else self._tooltip_text)
        if old and new and old.bind != new.bind:
            widget = self.widget
            widget.unbind(old.bind)
            widget.bind(new.bind, self._open_link)
        elif new and not old:
            self._enable_link()
        elif old and not new:
            self._disable_link(old.bind)

    def _enable_link(self):
        widget = self.widget
        widget.bind(self.__link.bind, self._open_link)
        widget.configure(cursor='hand2', fg=self.style.link.fg.default)

    def _disable_link(self, link_bind: str):
        widget = self.widget
        widget.unbind(link_bind)
        widget.configure(cursor='', fg=self.style.text.fg.default)

    def _open_link(self, event: Event):
        if not (link := self.link) or self.should_ignore(event):
            return
        link.open(event)

    # endregion


class Link(Text):
    def __init__(self, value: Any = '', link: Union[bool, str] = True, link_bind: str = LEFT_CLICK, **kwargs):
        super().__init__(value, link=link, link_bind=link_bind, **kwargs)


class Input(Interactive):
    widget: Entry
    string_var: Optional[StringVar] = None
    password_char: Optional[str] = None

    def __init__(
        self,
        value: Any = '',
        *,
        link: bool = None,
        password_char: str = None,
        justify_text: Union[str, Justify, None] = Justify.LEFT,
        callback: BindTarget = None,
        **kwargs
    ):
        super().__init__(justify_text=justify_text, **kwargs)
        self._value = str(value)
        self._link = link or link is None
        self._callback = callback
        if password_char:
            self.password_char = password_char

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
            **style.get_map('insert', state, insertbackground='bg'),  # Insert cursor (vertical line) color
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
        if self._link:  # TODO: Unify with Text's link handling
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

    def _open_link(self, event):
        if (value := self.value) and value.startswith(('http://', 'https://')):
            webbrowser.open(value)


class Multiline(Interactive):
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
        callback: BindTarget = None,
        **kwargs,
    ):
        super().__init__(justify_text=justify_text, **kwargs)
        self._value = str(value)
        self.scroll_y = scroll_y
        self.scroll_x = scroll_x
        self.auto_scroll = auto_scroll
        self.rstrip = rstrip
        self._callback = callback

    @property
    def style_config(self) -> dict[str, Any]:
        style, state = self.style, self.style_state
        config: dict[str, Any] = {
            'highlightthickness': 0,
            **style.get_map('input', state, bd='border_width', fg='fg', bg='bg', font='font', relief='relief'),
            **style.get_map('text', 'highlight', selectforeground='fg', selectbackground='bg'),
            **style.get_map('insert', insertbackground='bg'),
            **self._style_config,
        }
        config.setdefault('relief', 'sunken')
        return config

    def pack_into(self, row: Row, column: int):
        kwargs = self.style_config
        kwargs['takefocus'] = int(self.allow_focus)
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
            text.tag_add(justify.value, 1.0, 'end')  # noqa
        for pos in ('center', 'left', 'right'):
            text.tag_configure(pos, justify=pos)  # noqa

        self.pack_widget()
        if (callback := self._callback) is not None:
            text.bind('<Key>', self.normalize_callback(callback))

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

    @cached_property
    def widgets(self) -> list[BaseWidget]:
        return self.widget.widgets


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


def _clear_selection(widget: Union[Entry, Text], event: Event = None):
    widget.selection_clear()
