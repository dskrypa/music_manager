"""
View: Search results

:author: Doug Skrypa
"""

from PySimpleGUI import Text, Button, Combo, Image

from ...plex.query_parsing import PlexQuery, QueryParseError
from ..base_view import event_handler, RenderArgs, Event, EventData
from ..constants import LoadingSpinner
from ..elements import ExtInput
from ..options import GuiOptions
from ..popups.simple import popup_ok
from ..popups.text import popup_error
from ..progress import Spinner
from .elements import ResultTable
from .constants import LIB_TYPE_ENTITY_MAP
from .main import PlexView

__all__ = ['PlexSearchView']


class PlexSearchView(PlexView, view_name='search'):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.options = GuiOptions(self, submit=None)
        with self.options.next_row() as options:
            options.add_bool('allow_inst', 'Allow results that include instrumental versions of songs')
        with self.options.next_row() as options:
            options.add_input('escape', 'Escape regex special characters:', default='()')

        self.lib_section = section = self.last_section
        result_type = self.get_result_type(section)
        self.section_picker = Combo(list(self.lib_sections), section.title, enable_events=True, key='section')
        self.type_picker = Combo(
            LIB_TYPE_ENTITY_MAP[section.type], result_type.title(), enable_events=True, key='entity_types'
        )
        self.query = ExtInput('title~.*', size=(150, 1), key='query', focus=True)
        self.results = ResultTable(result_type.lower(), size=(900, self._window_size[1] - 160))

    @property
    def result_type(self):
        return self.results.result_type

    @result_type.setter
    def result_type(self, value: str):
        self.results.set_result_type(value.lower())

    def get_render_args(self) -> RenderArgs:
        full_layout, kwargs = super().get_render_args()

        search_row = [
            Text('Section:'),
            self.section_picker,
            self.type_picker,
            Text('Query:'),
            self.query,
            Button('Search', bind_return_key=True),
        ]
        layout = [
            [self.options.as_frame()],
            [search_row],
            [Image(key='spacer::1'), self.results, Image(key='spacer::2')],
        ]

        full_layout.extend(layout)
        return full_layout, kwargs

    def post_render(self):
        super().post_render()
        self.query.Widget.icursor(len(self.query.DefaultText))

    # def _output_size(self):
    #     win_w, win_h = self._window_size
    #     width, height = ((win_w - 180) // 7, (win_h - 214) // 16)
    #     return width, height

    @event_handler
    def section(self, event: Event, data: EventData):
        last_section = self.last_section
        if (section_title := self.section_picker.get()) != last_section.title:
            self.config['lib_section'] = section_title
            self.lib_section = section = self.lib_sections[section_title]
            if section.type != last_section.type:
                self.result_type = result_type = self.get_result_type(section)
                self.type_picker.update(result_type, LIB_TYPE_ENTITY_MAP[section.type])

    @event_handler
    def entity_types(self, event: Event, data: EventData):
        if (result_type := self.type_picker.get().lower()) != self.result_type:
            self.config[f'last_type:{self.lib_section.type}'] = self.result_type = result_type

    @event_handler
    def search(self, event: Event, data: EventData):
        self.options.parse(data)
        if (result_type := self.type_picker.get().lower()) != self.result_type:
            self.config[f'last_type:{self.lib_section.type}'] = self.result_type = result_type

        query = self.query.value
        try:
            kwargs = PlexQuery.parse(query, self.options['escape'], self.options['allow_inst'])
        except QueryParseError as e:
            return popup_error(str(e))
        else:
            self.log.debug(f'Parsed query={kwargs}')

        with Spinner(LoadingSpinner.blue_dots) as spinner:
            spinner.update()
            objects = self.plex.find_objects(result_type, **kwargs)
            spinner.update()
            if not objects:
                spinner.close()
                return popup_ok('No results.')

            self.results.show_results(objects, spinner)

    @event_handler
    def window_resized(self, event: Event, data: EventData):
        # data = {'old_size': old_size, 'new_size': new_size}
        # key_dict = self.window.key_dict
        self.results.expand(True, True)
