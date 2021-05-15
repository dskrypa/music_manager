"""
Main view for the Plex Manager GUI.  All other main window views extend this view.

Defines the top menu and some common configuration properties.

:author: Doug Skrypa
"""

from pathlib import Path

from PySimpleGUI import Menu

from ...plex.server import LocalPlexServer
from ..base_view import event_handler, GuiView, Event, EventData, RenderArgs
from ..popups.simple import popup_input_invalid

__all__ = ['PlexView']
DEFAULT_CONFIG = {'config_path': '~/.config/plexapi/config.ini'}


class PlexView(GuiView, view_name='plex', config_path='plex_gui_config.json', defaults=DEFAULT_CONFIG):
    def __init__(self, *, last_view: 'PlexView' = None, **kwargs):
        super().__init__(binds=kwargs.get('binds'))
        self.last_view = last_view
        self.menu = [
            ['&File', ['&Settings', 'E&xit']],
            # ['&Actions', []],
            ['&Help', ['&About']],
        ]
        # TODO: if config path doesn't exist, prompt for server_baseurl, username, server_path_root
        # TODO: if server_token isn't in the config, prompt for password
        self.plex = LocalPlexServer(config_path=self.config['config_path'])

    def get_render_args(self) -> RenderArgs:
        layout = [[Menu(self.menu)]]
        if self.__class__ is PlexView:
            pass

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
