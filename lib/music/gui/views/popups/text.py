"""
View: Text Popup

:author: Doug Skrypa
"""

from typing import Any

from PySimpleGUI import Element, Text, Button, Multiline

from .base import BasePopup

__all__ = ['TextPopup', 'popup_ok', 'popup_error']


class TextPopup(BasePopup, view_name='text_popup', primary=False):
    def __init__(
        self, text: str, title: str = '', button: str = None, multiline: bool = False, auto_size: bool = False, **kwargs
    ):
        super().__init__(binds={'<Escape>': 'Exit'}, title=title)
        self.text = text
        self.button = button
        self.multiline = multiline
        self.auto_size = auto_size
        self.kwargs = kwargs

    def get_render_args(self) -> tuple[list[list[Element]], dict[str, Any]]:
        size = self.kwargs.pop('size', (None, None))
        if self.auto_size and size == (None, None):
            lines = self.text.splitlines()
            width = max(map(len, lines))
            size = (width, len(lines))

        if self.multiline:
            layout = [[Multiline(self.text, key='txt::popup', size=size, disabled=True)]]
        else:
            layout = [[Text(self.text, key='txt::popup', size=size)]]
        if self.button:
            layout.append([Button(self.button, key='btn::popup')])
        return layout, {'title': self.title, **self.kwargs}


def popup_ok(*args, **kwargs):
    return TextPopup(*args, button='OK', **kwargs).get_result()


def popup_error(*args, **kwargs):
    return TextPopup(*args, button='OK', title='Error', **kwargs).get_result()
