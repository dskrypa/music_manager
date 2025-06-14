"""
View: Text Popup

:author: Doug Skrypa
"""

from functools import cached_property
from typing import Any

from FreeSimpleGUI import Element, Text, Button, Multiline, Input, Column

from ds_tools.images.utils import ImageType
from ..base_view import event_handler, RenderArgs
from ..elements.image import ExtendedImage
from ..window import Window
from ..icons import ICONS_DIR
from .base import BasePopup

__all__ = ['TextPopup', 'popup_ok', 'popup_error', 'TextInputPopup', 'popup_get_text', 'popup_warning']


def popup_ok(*args, **kwargs):
    return TextPopup(*args, button='OK', **kwargs).get_result()


def popup_error(*args, **kwargs):
    return TextPopup(*args, button='OK', title='Error', **kwargs).get_result()


def popup_warning(*args, **kwargs):
    img_path = ICONS_DIR.joinpath('exclamation-triangle-yellow.png')
    kwargs.setdefault('font', ('Helvetica', 20))
    return TextPopup(*args, button='OK', title='Warning', image=img_path, **kwargs).get_result()


def popup_get_text(prompt: str, title: str = '', strip: bool = True, password_char: str = '', **kwargs):
    return TextInputPopup(prompt, title=title, strip=strip, password_char=password_char, **kwargs).get_result()


class TextPopup(BasePopup, view_name='text_popup', primary=False):
    def __init__(
        self,
        text: str,
        title: str = '',
        *,
        button: str = None,
        multiline: bool = False,
        auto_size: bool = False,
        font: tuple[str, int] = None,
        image: ImageType = None,
        image_size: tuple[int, int] = None,
        **kwargs
    ):
        super().__init__(binds={'<Escape>': 'Exit'}, title=title, **kwargs)
        self.text = text
        self.button = button
        self.multiline = multiline
        self.auto_size = auto_size
        self.font = font
        self.image = image
        self.image_size = image_size if image_size else (100, 100) if image else None
        self.kwargs.setdefault('resizable', True)

    @cached_property
    def lines(self):
        return self.text.splitlines()

    @cached_property
    def longest_line(self):
        return max(map(len, self.lines))

    @cached_property
    def line_height(self):
        return int((10 if self.font is None else self.font[1]) * 1.8)  # Close enough approximation

    @cached_property
    def text_size(self):
        size = self.kwargs.pop('size', (None, None))
        if self.auto_size or size == (None, None):
            if self.multiline or len(self.lines) > 1:
                lines_shown = max(1, min(Window.get_screen_size()[1] // self.line_height, len(self.lines)) + 1)
            else:
                lines_shown = 1
            self.log.debug(f'Showing {lines_shown} lines, char width={self.longest_line}')
            size = (self.longest_line, lines_shown)
        return size

    def get_render_args(self) -> RenderArgs:
        kwargs = dict(key='txt::popup', size=self.text_size, font=self.font)
        text = Multiline(self.text, disabled=True, **kwargs) if self.multiline else Text(self.text, **kwargs)
        if self.image:
            layout = [[ExtendedImage(self.image, size=self.image_size, bind_click=False), text]]
        else:
            layout = [[text]]
        if self.button:
            button_col = Column([[Button(self.button, key='btn::popup', bind_return_key=True)]], justification='right')
            layout.append([button_col])
        return layout, {'title': self.title, **self.kwargs}


class TextInputPopup(BasePopup, view_name='text_input_popup', primary=False):
    def __init__(
        self,
        prompt: str,
        title: str = '',
        submit: str = 'Submit',
        font: tuple[str, int] = None,
        strip: bool = True,
        password_char: str = '',
        **kwargs
    ):
        super().__init__(binds={'<Escape>': 'Exit'}, title=title, **kwargs)
        self.prompt = prompt
        self.submit = submit
        self.font = font
        self.strip = strip
        self.password_char = password_char
        self.kwargs.setdefault('resizable', True)
        self.kwargs.setdefault('element_justification', 'center')

    def get_render_args(self) -> tuple[list[list[Element]], dict[str, Any]]:
        size = self.kwargs.pop('size', (None, None))
        layout = [
            [Text(self.prompt, key='prompt', size=size, font=self.font)],
            [Input('', key='value', size=size, font=self.font, password_char=self.password_char)],
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
