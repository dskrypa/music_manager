import logging

from cli_command_parser import Command, Counter, SubCommand, ParamGroup, Flag, Positional, Option, main  # noqa

from music.__version__ import __author_email__, __version__, __author__, __url__  # noqa

log = logging.getLogger(__name__)


class MusicManagerGui(Command, description='Music Manager GUI'):
    sub_cmd = SubCommand(required=False)
    with ParamGroup('Common') as group:
        verbose = Counter('-v', help='Increase logging verbosity (can specify multiple times)')
        match_log = Flag(help='Enable debug logging for the album match processing logger')

    def _init_command_(self):
        from ds_tools.logging import init_logging
        init_logging(self.verbose, names=None, millis=True, set_levels={'PIL': 30})

    def main(self):
        self.run_gui()

    def run_gui(self, init_event=None):
        from music.gui.music_manager_views.main import MainView

        self.patch_and_set_mode()

        try:
            MainView.start(
                title='Music Manager',
                resizable=True,
                size=(1700, 750),
                element_justification='center',
                init_event=init_event,
            )
        except Exception:
            log.critical('Exiting run_gui due to unhandled exception', exc_info=True)
            raise

    def patch_and_set_mode(self):
        from music.common.prompts import set_ui_mode, UIMode
        from music.files.patches import apply_mutagen_patches
        from music.gui.patches import patch_all

        apply_mutagen_patches()
        patch_all()
        # logging.getLogger('wiki_nodes.http.query').setLevel(logging.DEBUG)
        if self.match_log:
            from music.manager.wiki_match import mlog  # It may not have been imported before this point

            mlog.setLevel(logging.NOTSET)

        set_ui_mode(UIMode.GUI)


class Open(MusicManagerGui, help='Open directly to the Album view for the given path'):
    album_path = Positional(help='The path to the album to open')

    def main(self):
        self.run_gui(('init_view', {'view': 'album', 'path': self.album_path}))


class Clean(MusicManagerGui, help='Open directly to the Clean view for the given path'):
    path = Positional(nargs='+', help='The directory containing files to clean')
    with ParamGroup('Wait Options', mutually_exclusive=True):
        multi_instance_wait: int = Option('-w', default=1, help='Seconds to wait for multiple instances started at the same time to collaborate on paths')
        no_wait = Flag('-W', help='Do not wait for other instances')

    def main(self):
        if self.no_wait:
            clean_paths = self.path
        else:
            from music.manager.init_ipc import get_clean_paths

            if (clean_paths := get_clean_paths(self.multi_instance_wait, self.path)) is None:
                log.debug('Exiting non-primary clean process')
                return

        log.debug(f'Clean paths={clean_paths}')
        self.run_gui(('init_view', {'view': 'clean', 'path': clean_paths}))


class Configure(MusicManagerGui, help='Configure registry entries for right-click actions'):
    dry_run = Flag('-D', help='Print the actions that would be taken instead of taking them')

    def main(self):
        from music.registry import configure_music_manager_gui

        configure_music_manager_gui(self.dry_run)
