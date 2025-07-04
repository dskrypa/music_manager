"""
Main view for the Plex Manager GUI.  All other main window views extend this view.

Defines the top menu and some common configuration properties.

:author: Doug Skrypa
"""

from FreeSimpleGUI import Menu, Button, Column, Image
from plexapi.library import LibrarySection

from ds_tools.images.utils import image_to_bytes

from music.plex.config import config
from music.plex.server import LocalPlexServer
from ..base_view import event_handler, GuiView, Event, EventData, RenderArgs
from ..popups.simple import popup_input_invalid
from ..popups.text import popup_warning
from ..icons import ICONS_DIR
from .constants import LIB_TYPE_ENTITY_MAP

__all__ = ['PlexView']
DEFAULT_CONFIG = {'config_path': '~/.config/plexapi/config.ini'}


class PlexView(GuiView, view_name='plex', config_path='plex_gui_config.json', defaults=DEFAULT_CONFIG):
    # _log_clicks = True

    def __init__(self, *, plex: LocalPlexServer = None, **kwargs):
        super().__init__(**kwargs)
        self.menu = [['&File', ['&Settings', 'E&xit']]]
        self.plex: LocalPlexServer = plex or LocalPlexServer(config_path=self.config['config_path'])

    @property
    def last_section(self) -> LibrarySection:
        sections = self.plex.sections
        if last_section := self.config.get('lib_section'):
            try:
                return sections[last_section]
            except KeyError:
                self.log.warning(f'Last lib section={last_section!r} does not seem to exist')
        try:
            return sections[config.music_lib_name]
        except KeyError:
            self.log.warning(f'Configured music lib section={config.music_lib_name!r} does not seem to exist')

        for title, lib in sections.items():
            if lib.type == 'artist':
                return lib

        if sections:
            return next(iter(sections.values()))

        popup_warning('No library sections are available!')
        raise RuntimeError('No library sections are available!')

    def get_result_type(self, lib_section: LibrarySection = None):
        lib_section = lib_section or self.last_section
        section_type = lib_section.type
        if last_type := self.config.get(f'last_type:{section_type}'):
            return last_type
        entity_types = LIB_TYPE_ENTITY_MAP[section_type]
        return entity_types[0]

    def get_render_args(self) -> RenderArgs:
        try:
            layout = [[Menu(self.menu)]]
        except AttributeError:
            layout = []

        if self.__class__ is PlexView and not self._init_event:
            image = image_to_bytes(ICONS_DIR.joinpath('search.png'), size=(200, 200))
            button = Button(
                'Search', image_data=image, image_size=(210, 210), font=('Helvetica', 18), bind_return_key=True
            )
            inner_layout = [[Image(key='spacer::2', pad=(0, 0))], [button], [Image(key='spacer::1', pad=(0, 0))]]
            content = Column(
                inner_layout,
                vertical_alignment='center',
                justification='center',
                element_justification='center',
                expand_y=True,
                expand_x=True,
            )
            layout.append([content])

        kwargs = {'title': f'Plex Manager - {self.display_name}'}
        return layout, kwargs

    def post_render(self):
        for key, element in self.window.key_dict.items():
            if isinstance(key, str) and key.startswith('spacer::'):
                element.expand(True, True, True)

    @event_handler
    def init_view(self, event: Event, data: EventData):
        data = data[event]
        if (view := data['view']) == 'search':
            from .search import PlexSearchView

            return PlexSearchView(plex=self.plex)
        else:
            popup_input_invalid(f'Unexpected initial {view=}', logger=self.log)

    def _settings(self):
        options = super()._settings()
        with options.next_row():
            options.add_directory('server_path_root', 'Server Path Root', config.server_root)
        with options.next_row():
            options.add_input('music_lib_name', 'Music Lib Name', config.music_lib_name)
        return options

    @event_handler
    def settings(self, event: Event, data: EventData):
        from ..popups.settings import SettingsView

        results = SettingsView(self._settings(), private=['server_path_root', 'music_lib_name']).get_result()
        self.log.debug(f'Settings {results=}')
        if (server_path_root := results.get('server_path_root')) and server_path_root != config.server_root:
            config.server_root = server_path_root
        if (music_lib_name := results.get('music_lib_name')) and music_lib_name != config.music_lib_name:
            config.music_lib_name = music_lib_name
            config.clear_cached_properties('primary_lib_names')
            self.plex.clear_cached_properties('primary_sections', 'music')

    @event_handler
    def search(self, event: Event, data: EventData):
        from .search import PlexSearchView

        return PlexSearchView(plex=self.plex)
