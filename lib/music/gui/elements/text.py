"""
Text elements for PySimpleGUI

:author: Doug Skrypa
"""

import logging
import webbrowser
from functools import cached_property
from tkinter import Label, X, Y, BOTH
from typing import Union

from PySimpleGUI import Text, COLOR_SYSTEM_DEFAULT, pin

__all__ = ['ExtText']
log = logging.getLogger(__name__)


class ExtText(Text):
    TKText: Label

    def __init__(
        self,
        value='',
        *args,
        link: Union[bool, str] = None,
        tooltip: str = None,
        **kwargs,
    ):
        """
        :param value: The initial value to display
        :param args: Positional arguments to pass to :class:`PySimpleGUI.Text`
        :param link: Whether the displayed text should be hyperlinked to open a browser with the text as the URL, or the
          URL to open (default: link if the text starts with ``http://`` or ``https://``)
        :param tooltip: A tooltip to be displayed when hovering over this element.  If link / a link is detected, then
          additional information will be appended to this value.
        :param kwargs: Keyword arguments to pass to :class:`PySimpleGUI.Input`
        """
        self._orig_tooltip = tooltip
        self._link = link or link is None
        self.DisplayText = str(value)
        super().__init__(value, *args, tooltip=self._tooltip(), **kwargs)

    @property
    def url(self):
        if link := self._link:
            url = link if isinstance(link, str) else self.DisplayText
            return url if url.startswith(('http://', 'https://')) else None
        return None

    def _tooltip(self):
        if (url := self.url) and self._link:
            link_text = 'link' if self._link is True else url
            if tooltip := self._orig_tooltip:
                return f'{tooltip}; open {link_text} in browser with ctrl + click'
            return f'Open {link_text} in browser with ctrl + click'
        else:
            return self._orig_tooltip

    def _enable_link(self):
        if (label := self._tk_label) is not None:
            label.bind('<Control-Button-1>', self._open_link)
            if self.url is not None:
                label.configure(cursor='hand2')  # TODO: This does not seem to be working on update...

    @property
    def TKText(self):
        return self._tk_label

    @TKText.setter
    def TKText(self, label: Label):
        self._tk_label = label
        self._enable_link()

    @cached_property
    def pin(self):
        return pin(self)

    def style(self, background_color=None, text_color=None, font=None):
        kwargs = {}
        if background_color not in (None, COLOR_SYSTEM_DEFAULT):
            kwargs['background'] = background_color
        if text_color not in (None, COLOR_SYSTEM_DEFAULT):
            kwargs['fg'] = text_color
        if font is not None:
            kwargs['font'] = font
        if kwargs:
            self._tk_label.configure(**kwargs)

    def update_link(self, link: Union[bool, str]):
        old_link = self._link
        self._link = link
        self.set_tooltip(self._tooltip())
        if link and not old_link:
            self._enable_link()
        elif old_link and not link:
            self._tk_label.unbind('<Control-Button-1>')
            self._tk_label.configure(cursor='')

    def update(
        self, value=None, link: Union[bool, str] = None, background_color=None, text_color=None, font=None, visible=None
    ):
        if value is not None:
            self.value = value
        if background_color or text_color or font:
            self.style(background_color, text_color, font)
        if link is not None:
            self.update_link(link)
        if visible is not None:
            self.update_visibility(visible)

    def update_visibility(self, visible: bool):
        if visible:
            self.show()
        else:
            self.hide()

    def hide(self, force: bool = False):
        if force or self._visible:
            self._visible = False
            # if pinned := self.__dict__.get('pin'):
            #     # log.debug(f'Hiding pinned column for {self}')
            #     if col_frame := pinned.TKColFrame:
            #         col_frame.pack_forget()
            #         if parent := pinned.ParentPanedWindow:
            #             parent.remove(col_frame)
            # else:
                # log.debug(f'Hiding label for {self}')
            self._tk_label.pack_forget()

    def show(self, force: bool = False):
        if force or not self._visible:
            self._visible = True
            # if pinned := self.__dict__.get('pin'):
            #     # log.debug(f'Showing pinned column for {self}')
            #     if col_frame := pinned.TKColFrame:
            #         x, y, ex_x, ex_y = *pinned.pad_used, pinned.ExpandX, pinned.ExpandY  # noqa
            #         col_frame.pack(padx=x, pady=y, fill=BOTH if ex_x and ex_y else X if ex_x else Y if ex_y else None)
            #         if parent := pinned.ParentPanedWindow:
            #             parent.add(col_frame)
            # else:
            x, y = self.pad_used
            #     # log.debug(f'Showing label for {self} with {x=} {y=}')
            self._tk_label.pack(padx=x, pady=y)

    @property
    def value(self):
        return self.DisplayText

    @value.setter
    def value(self, value):
        value = str(value)
        self.DisplayText = value
        self.TKStringVar.set(value)

    def _open_link(self, event):
        if (url := self.url) is not None:
            webbrowser.open(url)
