from cli_command_parser import Command, Counter, main

from ..__version__ import __author_email__, __version__, __author__, __url__  # noqa


class PlexManagerGui(Command, description='Plex Manager GUI'):
    verbose = Counter('-v', help='Increase logging verbosity (can specify multiple times)')

    def main(self):
        from ds_tools.logging import init_logging

        init_logging(self.verbose, names=None, millis=True, set_levels={'PIL': 30})

        from music.common.prompts import set_ui_mode, UIMode
        from music.files.patches import apply_mutagen_patches
        from music.gui.patches import patch_all
        from music.gui.plex_views.main import PlexView

        apply_mutagen_patches()
        patch_all()
        set_ui_mode(UIMode.GUI)

        start_kwargs = dict(title='Plex Manager', resizable=True, size=(1700, 750), element_justification='center')
        start_kwargs['init_event'] = ('init_view', {'view': 'search'})
        # start_kwargs['init_event'] = ('init_view', {'view': 'player'})
        PlexView.start(**start_kwargs)
