"""
View: Search results

:author: Doug Skrypa
"""

from PySimpleGUI import Text, Button, Combo, Multiline

from ...plex.utils import parse_filters
from ..base_view import event_handler, RenderArgs, Event, EventData
from ..constants import LoadingSpinner
from ..elements.inputs import ExtInput
from ..options import GuiOptions
from ..popups.simple import popup_ok
from ..progress import Spinner
from .main import PlexView

__all__ = ['PlexSearchView']

LIB_TYPE_ENTITY_MAP = {
    'movie': ('Movie',),
    'show': ('Show', 'Season', 'Episode'),
    'artist': ('Track', 'Artist', 'Album'),
    'photo': ('Album', 'Photo'),
}


class PlexSearchView(PlexView, view_name='search'):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.options = GuiOptions(self, submit=None)
        with self.options.next_row() as options:
            options.add_bool('allow_inst', 'Allow results that include instrumental versions of songs')
        with self.options.next_row() as options:
            options.add_input('escape', 'Escape regex special characters:', default='()')

    def get_render_args(self) -> RenderArgs:
        full_layout, kwargs = super().get_render_args()

        last_section = self.last_section
        entity_types = LIB_TYPE_ENTITY_MAP[last_section.type]
        search_row = [
            Text('Section:'),
            Combo(list(self.lib_sections), last_section.title, enable_events=True, key='section'),
            Combo(entity_types, entity_types[0], enable_events=True, key='entity_types'),
            ExtInput('', size=(50, 1), key='title'),
            Text('Filter:'),
            ExtInput('', size=(100, 1), key='filters'),
            Button('Search', bind_return_key=True),
        ]
        layout = [
            [self.options.as_frame()],
            [search_row],
            [Multiline(size=self._output_size(), key='output', autoscroll=True)],
        ]

        full_layout.extend(layout)
        return full_layout, kwargs

    def _output_size(self):
        win_w, win_h = self._window_size
        width, height = ((win_w - 180) // 7, (win_h - 214) // 16)
        return width, height

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
        self.options.parse(data)
        window_ele_dict = self.window.key_dict
        obj_type = window_ele_dict['entity_types'].get().lower()  # noqa
        title = window_ele_dict['title'].value  # noqa
        filters = window_ele_dict['filters'].value  # noqa
        obj_type, kwargs = parse_filters(obj_type, title, filters, self.options['escape'], self.options['allow_inst'])
        objects = self.plex.find_objects(obj_type, **kwargs)
        if not objects:
            return popup_ok('No results.')

        output = window_ele_dict['output']  # type: Multiline  # noqa
        for i, obj in enumerate(objects):
            output.update(repr(obj) + '\n', append=i)  # noqa
