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

LIB_TYPE_CONTENT_MAP = {
    'movie': ('movie',),
    'show': ('show', 'season', 'episode'),
    'artist': ('artist', 'album', 'track'),
    'photo': ('album', 'photo'),
}


class PlexSearchView(PlexView, view_name='search'):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def get_render_args(self) -> RenderArgs:
        full_layout, kwargs = super().get_render_args()

        last_section = self.last_section
        contents = LIB_TYPE_CONTENT_MAP[last_section.type]
        search_row = [
            Text('Section:'),
            Combo(list(self.lib_sections), last_section.title, enable_events=True, key='section'),
            Combo(contents, contents[0], enable_events=True, key='section_grouping'),
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
        pass  # TODO: update section_grouping options based on new section value

    @event_handler
    def search(self, event: Event, data: EventData):
        pass
