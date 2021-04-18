"""
View: Test Popup

:author: Doug Skrypa
"""

from typing import Any

from PySimpleGUI import Element, Multiline

from .base import BasePopup, Event, EventData, event_handler

__all__ = ['KeypressTesterPopup']


class KeypressTesterPopup(BasePopup, view_name='keypress_tester_popup', primary=False):
    def __init__(self, title: str = 'Test', size=(50, 20), **kwargs):
        super().__init__(title=title)
        self.kwargs = kwargs
        self.size = size
        self.output = Multiline('', key='output', size=self.size, disabled=True, autoscroll=True)
        # self.binds['<Control-Left>'] = 'bound'
        # self.binds['<Control-Right>'] = 'bound'
        # self.binds['<Control-Button-1>'] = 'bound'

    def get_render_args(self) -> tuple[list[list[Element]], dict[str, Any]]:
        layout = [[self.output]]
        return layout, {'title': self.title, 'return_keyboard_events': True, **self.kwargs}

    @event_handler(default=True)
    def default(self, event: Event, data: EventData):
        self.output.update(f'{event}\n', append=True)

    @event_handler
    def bound(self, event: Event, data: EventData):
        self.output.update(f'BOUND: [{event}]\n', append=True)


def test_keys(*args, **kwargs):
    return KeypressTesterPopup(*args, **kwargs).get_result()
