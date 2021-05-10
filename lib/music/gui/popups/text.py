"""
View: Text Popup

:author: Doug Skrypa
"""

from typing import Any

from PySimpleGUI import Element, Text, Button, Multiline, Input

from ..base_view import event_handler
from .base import BasePopup

__all__ = ['TextPopup', 'popup_ok', 'popup_error', 'TextInputPopup', 'popup_get_text']


def popup_ok(*args, **kwargs):
    return TextPopup(*args, button='OK', **kwargs).get_result()


def popup_error(*args, **kwargs):
    return TextPopup(*args, button='OK', title='Error', **kwargs).get_result()


def popup_get_text(prompt: str, title: str = '', strip: bool = True, **kwargs):
    return TextInputPopup(prompt, title=title, strip=strip, **kwargs).get_result()


class TextPopup(BasePopup, view_name='text_popup', primary=False):
    def __init__(
        self,
        text: str,
        title: str = '',
        button: str = None,
        multiline: bool = False,
        auto_size: bool = False,
        font: tuple[str, int] = None,
        **kwargs
    ):
        super().__init__(binds={'<Escape>': 'Exit'}, title=title)
        self.text = text
        self.button = button
        self.multiline = multiline
        self.auto_size = auto_size
        self.font = font
        self.kwargs = kwargs

    def get_render_args(self) -> tuple[list[list[Element]], dict[str, Any]]:
        size = self.kwargs.pop('size', (None, None))
        if self.auto_size or size == (None, None):
            lines = self.text.splitlines()
            width = max(map(len, lines))
            line_height = int((10 if self.font is None else self.font[1]) * 1.8)  # Close enough approximation
            lines_shown = max(1, min(self.window.get_screen_size()[1] // line_height, len(lines)) + 1)
            self.log.debug(f'Showing {lines_shown} lines')
            size = (width, lines_shown)

        if self.multiline:
            layout = [[Multiline(self.text, key='txt::popup', size=size, disabled=True, font=self.font)]]  # noqa
        else:
            layout = [[Text(self.text, key='txt::popup', size=size, font=self.font)]]
        if self.button:
            layout.append([Button(self.button, key='btn::popup')])
        return layout, {'title': self.title, **self.kwargs}


class TextInputPopup(BasePopup, view_name='text_input_popup', primary=False):
    def __init__(
        self,
        prompt: str,
        title: str = '',
        submit: str = 'Submit',
        font: tuple[str, int] = None,
        strip: bool = True,
        **kwargs
    ):
        super().__init__(binds={'<Escape>': 'Exit'}, title=title)
        self.prompt = prompt
        self.submit = submit
        self.font = font
        self.strip = strip
        self.kwargs = kwargs

    def get_render_args(self) -> tuple[list[list[Element]], dict[str, Any]]:
        size = self.kwargs.pop('size', (None, None))
        layout = [
            [Text(self.prompt, key='prompt', size=size, font=self.font)],
            [Input('', key='value', size=size, font=self.font)],
            [Button(self.submit, key='submit', bind_return_key=True)],
        ]
        return layout, {'title': self.title, **self.kwargs}

    @event_handler
    def submit(self, event: str, data: dict[str, Any]):
        if result := self.window['value'].get():
            if self.strip:
                result = result.strip()
            self.result = result
        raise StopIteration
