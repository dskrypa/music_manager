"""
Main view for the Plex Manager GUI.  All other main window views extend this view.

Defines the top menu and some common configuration properties.

:author: Doug Skrypa
"""

from functools import cached_property
from pathlib import Path

from plexapi.library import LibrarySection
from PySimpleGUI import Menu, Button, Column, Image

from ...common.images import image_to_bytes
from ...plex.server import LocalPlexServer
from ..base_view import event_handler, GuiView, Event, EventData, RenderArgs
from ..popups.simple import popup_input_invalid
from ..popups.text import popup_warning

__all__ = ['PlexView']
DEFAULT_CONFIG = {'config_path': '~/.config/plexapi/config.ini'}
ICONS_DIR = Path(__file__).resolve().parents[4].joinpath('icons')


class PlexView(GuiView, view_name='plex', config_path='plex_gui_config.json', defaults=DEFAULT_CONFIG):
    def __init__(self, *, plex: LocalPlexServer = None, **kwargs):
        super().__init__(**kwargs)
        self.menu = [
            ['&File', ['&Settings', 'E&xit']],
            # ['&Actions', []],
            ['&Help', ['&About']],
        ]
        self.plex: LocalPlexServer = plex or LocalPlexServer(config_path=self.config['config_path'])

    @cached_property
    def lib_sections(self) -> dict[str, LibrarySection]:
        return {lib.title: lib for lib in self.plex._library.sections()}

    @property
    def last_section(self) -> LibrarySection:
        lib_sections = self.lib_sections
        if last_section := self.config.get('lib_section'):
            try:
                return lib_sections[last_section]
            except KeyError:
                self.log.warning(f'Last lib section={last_section!r} does not seem to exist')
        try:
            return lib_sections[self.plex.music_library]
        except KeyError:
            self.log.warning(f'Configured music lib section={self.plex.music_library!r} does not seem to exist')

        for title, lib in lib_sections.items():
            if lib.type == 'artist':
                return lib

        if lib_sections:
            return next(iter(lib_sections.values()))

        popup_warning('No library sections are available!')
        raise RuntimeError('No library sections are available!')

    def get_render_args(self) -> RenderArgs:
        layout = [[Menu(self.menu)]]
        if self.__class__ is PlexView:
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
        if (view := data['view']) == 'album':
            pass
        else:
            popup_input_invalid(f'Unexpected initial {view=!r}', logger=self.log)

    def _settings(self):
        options = super()._settings()
        with options.next_row():
            options.add_directory('server_path_root', 'Server Path Root', self.plex.server_root)
        with options.next_row():
            options.add_input('music_lib_name', 'Music Lib Name', self.plex.music_library)
        return options

    @event_handler
    def settings(self, event: Event, data: EventData):
        from ..popups.settings import SettingsView

        results = SettingsView(self._settings(), private=['server_path_root', 'music_lib_name']).get_result()
        self.log.debug(f'Settings {results=}')
        if (server_path_root := results.get('server_path_root')) and server_path_root != self.plex.server_root:
            self.plex._set_config('custom', 'server_path_root', server_path_root)
            self.plex.server_root = Path(server_path_root)
        if (music_lib_name := results.get('music_lib_name')) and music_lib_name != self.plex.music_library:
            self.plex._set_config('custom', 'music_lib_name', music_lib_name)
            self.plex.music_library = music_lib_name

    @event_handler
    def search(self, event: Event, data: EventData):
        from .search import PlexSearchView

        return PlexSearchView(plex=self.plex)
