"""
View: Search results

:author: Doug Skrypa
"""

from math import ceil

from PySimpleGUI import Text, Button, Combo, Multiline, Column

from ...plex.query_parsing import PlexQuery, QueryParseError
from ..base_view import event_handler, RenderArgs, Event, EventData
from ..constants import LoadingSpinner
from ..elements.inputs import ExtInput
from ..options import GuiOptions
from ..popups.simple import popup_ok
from ..popups.text import popup_error
from ..progress import Spinner
from .elements import TrackRow
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
        self.track_rows = [TrackRow() for _ in range(100)]
        win_w, win_h = self._window_size
        self.results = Column(
            [[tr.column] for tr in self.track_rows],
            scrollable=True,
            vertical_scroll_only=True,
            key='results',
            expand_x=True,
            expand_y=True,
            size=(800, win_h - 160),
            element_justification='center',
        )

    def get_render_args(self) -> RenderArgs:
        full_layout, kwargs = super().get_render_args()

        last_section = self.last_section
        entity_types = LIB_TYPE_ENTITY_MAP[last_section.type]
        search_row = [
            Text('Section:'),
            Combo(list(self.lib_sections), last_section.title, enable_events=True, key='section'),
            Combo(entity_types, entity_types[0], enable_events=True, key='entity_types'),
            Text('Query:'),
            ExtInput('title~.*', size=(150, 1), key='query'),
            Button('Search', bind_return_key=True),
        ]
        layout = [
            [self.options.as_frame()],
            [search_row],
            # [Multiline(size=self._output_size(), key='output', autoscroll=True)],
            [self.results],
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
        query = window_ele_dict['query'].value  # noqa
        try:
            kwargs = PlexQuery.parse(query, self.options['escape'], self.options['allow_inst'])
        except QueryParseError as e:
            return popup_error(str(e))
        else:
            self.log.debug(f'Parsed query={kwargs}')

        with Spinner(LoadingSpinner.blue_dots) as spinner:
            spinner.update()
            objects = self.plex.find_objects(obj_type, **kwargs)
            spinner.update()
            if not objects:
                spinner.close()
                return popup_ok('No results.')

            obj_count = len(objects)
            self.log.info(f'Found {obj_count} {obj_type}s for {query=}')
            # pages = ceil(obj_count / 100)
            # TODO: Pagination
            # TODO: Sorting
            for row, obj in spinner(zip(self.track_rows, objects)):
                row.update(obj)

            if obj_count < 100:
                for i in range(obj_count, 100):
                    self.track_rows[i].clear()

        # TODO: Table instead?  Need column headers.
        try:
            self.results.TKColFrame.canvas.yview_moveto(0)  # noqa
        except Exception:
            pass
        self.results.expand(expand_y=True)  # including expand_x=True in this call results in no vertical scroll
        self.results.expand(expand_x=True)  # results in shorter y, but scroll works...  probably need to calculate proper height for init
        self.results.contents_changed()

        # output = window_ele_dict['output']  # type: Multiline  # noqa
        # for i, obj in enumerate(objects):
        #     output.update(repr(obj) + '\n', append=i)  # noqa

    @event_handler
    def window_resized(self, event: Event, data: EventData):
        # data = {'old_size': old_size, 'new_size': new_size}
        key_dict = self.window.key_dict
        self.results.expand(True, True)
