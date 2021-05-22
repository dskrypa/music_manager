"""
Text elements for PySimpleGUI

:author: Doug Skrypa
"""

import logging
import webbrowser
from tkinter import Label
from typing import Union

from PySimpleGUI import Text

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
            url = link if isinstance(link, str) else self.value
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

    def update(self, *args, link: Union[bool, str] = None, **kwargs):
        super().update(*args, **kwargs)
        if link is not None:
            old_link = self._link
            self._link = link
            self.set_tooltip(self._tooltip())
            if link and not old_link:
                self._enable_link()
            elif old_link and not link:
                self._tk_label.unbind('<Control-Button-1>')
                self._tk_label.configure(cursor='')

    @property
    def value(self):
        return self.get()

    def _open_link(self, event):
        if (url := self.url) is not None:
            webbrowser.open(url)
