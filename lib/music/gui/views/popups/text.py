"""
View: Text Popup

:author: Doug Skrypa
"""

from typing import Any

from PySimpleGUI import Element, Text, Button

from ..base import event_handler, GuiView

__all__ = ['TextPopup', 'popup_ok', 'popup_error']


class TextPopup(GuiView, view_name='text_popup', primary=False):
    def __init__(self, text: str, title: str = '', button: str = None, **kwargs):
        super().__init__(binds={'<Escape>': 'Exit'})
        self.text = text
        self.title = title
        self.button = button
        self.kwargs = kwargs

    @event_handler(default=True)  # noqa
    def default(self, event: str, data: dict[str, Any]):
        raise StopIteration

    def get_render_args(self) -> tuple[list[list[Element]], dict[str, Any]]:
        size = self.kwargs.pop('size', (None, None))
        layout = [[Text(self.text, key='txt::popup', size=size)]]
        if self.button:
            layout.append([Button(self.button, key='btn::popup')])
        return layout, {'title': self.title, **self.kwargs}


def popup_ok(*args, **kwargs):
    popup = TextPopup(*args, button='OK', **kwargs)
    popup.render()
    popup.run()


def popup_error(*args, **kwargs):
    popup = TextPopup(*args, button='OK', title='Error', **kwargs)
    popup.render()
    popup.run()
