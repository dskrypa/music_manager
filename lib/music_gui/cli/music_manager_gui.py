"""
Music Manager GUI that uses `tk_gui <https://github.com/dskrypa/tk_gui>`__.
"""

import logging
from pathlib import Path
from multiprocessing import set_start_method

from cli_command_parser import Command, Counter, SubCommand, ParamGroup, Flag, Positional, Option, main
from cli_command_parser.inputs import Path as IPath

log = logging.getLogger(__name__)


class MusicManagerGui(Command, description='Music Manager GUI'):
    sub_cmd = SubCommand(required=False)
    with ParamGroup('Common') as group:
        verbose = Counter('-v', help='Increase logging verbosity (can specify multiple times)')
        match_log = Flag(help='Enable debug logging for the album match processing logger')

    def _init_command_(self):
        from ds_tools.logging import init_logging

        init_logging(self.verbose, names=None, millis=True, set_levels={'PIL': 30}, set_tz=False)
        set_start_method('spawn')

    def main(self):
        self.run_gui()

    def run_gui(self, view_cls=None, **kwargs):
        from music_gui.manager_views.base import InitialView

        self.patch_and_set_mode()

        if not view_cls:
            view_cls = InitialView
        try:
            view_cls.run_all(**kwargs)
        except Exception:
            log.critical('Exiting run_gui due to unhandled exception', exc_info=True)
            raise

    def patch_and_set_mode(self):
        from music.common.prompts import set_ui_mode, UIMode
        from music.files.patches import apply_mutagen_patches

        apply_mutagen_patches()
        set_ui_mode(UIMode.TK_GUI)
        # logging.getLogger('wiki_nodes.http.query').setLevel(logging.DEBUG)
        if self.match_log:
            from music.manager.wiki_match import mlog  # It may not have been imported before this point

            mlog.setLevel(logging.NOTSET)


class Open(MusicManagerGui, help='Open directly to the Album view for the given path'):
    path: Path = Positional(type=IPath(), help='Path to an album or track')
    view = Option('-V', choices=('album', 'tags'), default='album', help='The view to use for the specified album')

    def main(self):
        from music_gui.manager_views.album import AlbumView
        from music_gui.manager_views.tracks import SelectableSongFileView

        view_cls = AlbumView if self.view == 'album' else SelectableSongFileView
        self.run_gui(view_cls, album=self.path)


class Clean(MusicManagerGui, help='Open directly to the Clean view for the given path'):
    path = Positional(nargs='+', help='The directory containing files to clean')
    with ParamGroup('Wait Options', mutually_exclusive=True):
        multi_instance_wait: float = Option(
            '-w', default=0.5, help='Seconds to wait for multiple instances started together to collaborate on paths'
        )
        no_wait = Flag('-W', help='Do not wait for other instances')

    def main(self):
        if self.no_wait:
            clean_paths = self.path
        else:
            from music.manager.init_ipc import get_clean_paths

            # While extremely rare, if this fails / ends up in a bad state, it may be necessary to manually delete
            # ~/AppData/Local/Temp/ds_tools_cache/music_manager/active_pid_port.txt and/or init.lock in the same dir
            if (clean_paths := get_clean_paths(self.multi_instance_wait, self.path)) is None:
                log.debug('Exiting non-primary clean process')
                return

        from music_gui.manager_views.clean import CleanView

        log.debug(f'Clean paths={clean_paths}')
        self.run_gui(CleanView, path_or_paths=clean_paths)


class Configure(MusicManagerGui, help='Configure registry entries for right-click actions'):
    dry_run = Flag('-D', help='Print the actions that would be taken instead of taking them')

    def main(self):
        try:
            from music.registry import configure_music_manager_gui
        except ImportError:
            log.error('The configure action is only currently supported on Windows')
        else:
            configure_music_manager_gui(self.dry_run, ' (New)')


if __name__ == '__main__':
    main()
