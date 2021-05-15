"""
View: Options

:author: Doug Skrypa
"""

from functools import partial
from typing import Any, Iterable

from PySimpleGUI import Element

from ..base_view import event_handler, Event, EventData
from ..options import GuiOptions, SingleParsingError, MultiParsingError
from ..utils import update_color
from .base import BasePopup

__all__ = ['OptionsView']


class OptionsView(BasePopup, view_name='options', primary=False):
    def __init__(self, options: GuiOptions, title: str = 'Options', **kwargs):
        super().__init__(binds={'<Escape>': 'Exit'}, title=title, **kwargs)
        self._failed_validation = {}
        self.options = options

    def get_render_args(self) -> tuple[list[list[Element]], dict[str, Any]]:
        layout = self.options.layout('submit')
        return layout, {'title': self.title}

    @event_handler
    def submit(self, event: Event, data: EventData):
        try:
            self.result = self.options.parse(data)
        except SingleParsingError as e:
            return self._mark_invalid([e])
        except MultiParsingError as e:
            return self._mark_invalid(e.errors)
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
