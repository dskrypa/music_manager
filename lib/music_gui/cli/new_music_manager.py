"""

"""

import logging
from pathlib import Path

from cli_command_parser import Command, Counter, SubCommand, ParamGroup, Flag, Positional, Option, inputs, main

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
    path: Path = Positional(type=inputs.Path(), help='Path to an album or track')
    view = Option('-V', choices=('album', 'tags'), default='album', help='The view to use for the specified album')

    def main(self):
        from music_gui.manager_views.album import AlbumView
        from music_gui.manager_views.tracks import SelectableSongFileView

        view_cls = AlbumView if self.view == 'album' else SelectableSongFileView
        self.run_gui(view_cls, album=self.path)


# class Configure(MusicManagerGui, help='Configure registry entries for right-click actions'):
#     dry_run = Flag('-D', help='Print the actions that would be taken instead of taking them')
#
#     def main(self):
#         configure(self.dry_run)
