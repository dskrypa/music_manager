"""
View: Search results

:author: Doug Skrypa
"""

from functools import partial, cached_property

from PySimpleGUI import Text, HorizontalSeparator, Column, Button, Listbox, Combo

from ..base_view import event_handler, RenderArgs, Event, EventData
from ..constants import LoadingSpinner
from ..elements.inputs import ExtInput
from ..popups.simple import popup_ok
from ..popups.text import popup_error, popup_get_text
from ..progress import Spinner
from .main import PlexView

__all__ = ['PlexSearchView']

LIB_TYPE_ENTITY_MAP = {
    'movie': ('Movie',),
    'show': ('Show', 'Season', 'Episode'),
    'artist': ('Artist', 'Album', 'Track'),
    'photo': ('Album', 'Photo'),
}


class PlexSearchView(PlexView, view_name='search'):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def get_render_args(self) -> RenderArgs:
        full_layout, kwargs = super().get_render_args()

        last_section = self.last_section
        entity_types = LIB_TYPE_ENTITY_MAP[last_section.type]
        search_row = [
            Text('Section:'),
            Combo(list(self.lib_sections), last_section.title, enable_events=True, key='section'),
            Combo(entity_types, entity_types[0], enable_events=True, key='entity_types'),
            ExtInput('', size=(100, 1), key='query'),
            Button('Search'),
        ]
        layout = [
            [search_row],
        ]

        full_layout.extend(layout)
        return full_layout, kwargs

    @event_handler
    def section(self, event: Event, data: EventData):
        window_ele_dict = self.window.key_dict
        section_title = window_ele_dict['section'].get()  # noqa
        last_section = self.last_section
        if section_title != last_section.title:
            self.config['lib_section'] = section_title
            section = self.lib_sections[section_title]
            if section.type != last_section.type:
                entity_types = LIB_TYPE_ENTITY_MAP[section.type]
                window_ele_dict['entity_types'].update(entity_types[0], entity_types)  # noqa

    @event_handler
    def search(self, event: Event, data: EventData):
        pass
