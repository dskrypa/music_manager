"""
View: Settings

:author: Doug Skrypa
"""

from functools import partial
from typing import Any, Iterable

from PySimpleGUI import Element, Submit, theme_list, theme

from ..base_view import event_handler, Event, EventData
from ..options import GuiOptions, SingleParsingError, MultiParsingError
from ..utils import update_color
from .base import BasePopup

__all__ = ['SettingsView']


class SettingsView(BasePopup, view_name='settings', primary=False):
    def __init__(self):
        super().__init__(binds={'<Escape>': 'Exit'})
        self._failed_validation = {}
        self.options = GuiOptions(self, submit='Save', title=None)
        with self.options.next_row() as options:
            options.add_bool('remember_pos', 'Remember Last Window Position', self.config['remember_pos'])
        with self.options.next_row() as options:
            options.add_dropdown('theme', 'Theme', theme_list(), self.config['theme'])
        with self.options.next_row() as options:
            options.add_directory('output_base_dir', 'Output Directory', self.config['output_base_dir'])

    def get_render_args(self) -> tuple[list[list[Element]], dict[str, Any]]:
        layout = self.options.layout('save')
        layout[-1].append(Submit('Apply', key='apply'))
        return layout, {'title': 'Settings'}

    @event_handler('save')
    def apply(self, event: Event, data: EventData):
        try:
            self.options.parse(data)
        except SingleParsingError as e:
            return self._mark_invalid([e])
        except MultiParsingError as e:
            return self._mark_invalid(e.errors)

        auto_save = self.config.auto_save
        self.config.auto_save = False
        try:
            for key, val in self.options.items():
                if val != self.config.get(key):
                    if key == 'theme':
                        self.log.info(f'Changing theme from {self.config[key]!r} to {val!r}')
                        theme(val)
                        self.window.close()
                        if event != 'save':
                            self.render()
                        if parent := self.parent:
                            parent.render()

                    self.config[key] = val
        except Exception:
            raise
        else:
            self.config.save()
        finally:
            self.config.auto_save = auto_save

        if event == 'save':
            raise StopIteration

    def _mark_invalid(self, errors: Iterable[SingleParsingError]):
        for error in errors:
            element = self.window[error.key]
            update_color(element, '#FFFFFF', '#781F1F')
            self._failed_validation[error.key] = element
            element.TKEntry.bind('<Key>', partial(self._edited_field, error.key))

    def _edited_field(self, key: str, event):
        self.log.debug(f'_edited_field({key=}, {event=})')
        if element := self._failed_validation.pop(key, None):
            element.TKEntry.unbind('<Key>')
            update_color(element, element.TextColor, element.BackgroundColor)
