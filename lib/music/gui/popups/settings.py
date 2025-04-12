"""
View: Settings

:author: Doug Skrypa
"""

from functools import partial
from typing import TYPE_CHECKING, Any, Iterable, Collection

from FreeSimpleGUI import Element, Submit, theme, Listbox

from ..base_view import event_handler, Event, EventData
from ..options import GuiOptions, SingleParsingError, MultiParsingError
from ..utils import update_color
from .base import BasePopup
from .text import popup_get_text

if TYPE_CHECKING:
    import tkinter

__all__ = ['SettingsView']


class SettingsView(BasePopup, view_name='settings', primary=False):
    def __init__(self, options: GuiOptions, private: Collection[str] = None, **kwargs):
        super().__init__(binds={'<Escape>': 'Exit'}, **kwargs)
        self._failed_validation = {}
        self.options = options
        self.private = set(private) if private else set()
        self.result = {}

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
                if key in self.private:
                    self.result[key] = val
                elif val != self.config.get(key):
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

    @event_handler('btn::*')
    def add_to_list(self, event: Event, data: EventData):
        field = event.split('::', 1)[1]
        list_box = self.window[f'opt::{field}']
        if not isinstance(list_box, Listbox):
            return
        prompt_name = self.options.options[field]['prompt_name']
        # label = self.window[f'lbl::{field}'].get()
        if not (new_value := popup_get_text(f'Enter a new {prompt_name} value to add', title=f'Add {prompt_name}')):
            return
        indexes = list(list_box.get_indexes())
        values = list_box.Values or []
        values.append(new_value)
        indexes.append(len(values) - 1)
        list_box.update(values, set_to_index=indexes)
        tk_list_box = list_box.TKListbox  # type: tkinter.Listbox
        height = tk_list_box.cget('height')
        if (val_count := len(values)) and val_count != height:
            tk_list_box.configure(height=val_count)
