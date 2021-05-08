"""
View: Settings

:author: Doug Skrypa
"""

from typing import Any

from PySimpleGUI import Element, Submit

from ...options import GuiOptions
from ..base import event_handler, Event, EventData
from .base import BasePopup

__all__ = ['SettingsView']


class SettingsView(BasePopup, view_name='settings', primary=False):
    def __init__(self):
        super().__init__(binds={'<Escape>': 'Exit'})
        self.options = GuiOptions(self, submit='Save', title=None)
        self.options.add_bool('remember_pos', 'Remember Last Window Position', self.state['remember_pos'])

    def get_render_args(self) -> tuple[list[list[Element]], dict[str, Any]]:
        layout = self.options.layout('save')
        layout[-1].append(Submit('Apply', key='apply'))
        return layout, {'title': 'Settings'}

    @event_handler('save')
    def apply(self, event: Event, data: EventData):
        self.options.parse(data)
        auto_save = self.state.auto_save
        self.state.auto_save = False
        try:
            for key, val in self.options.items():
                if val != self.state.get(key):
                    self.state[key] = val
        except Exception:
            raise
        else:
            self.state.save()
        finally:
            self.state.auto_save = auto_save

        if event == 'save':
            raise StopIteration
