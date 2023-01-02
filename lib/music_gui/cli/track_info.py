import logging
from pathlib import Path

from cli_command_parser import Command, Counter, ParamGroup, Positional, inputs as i, main

from music.__version__ import __author_email__, __version__, __author__, __url__  # noqa

log = logging.getLogger(__name__)


class TrackInfoGui(Command, description='Music Manager GUI - Track Info'):
    path: Path = Positional(type=i.Path(), help='Path to an album or track')
    with ParamGroup('Common') as group:
        verbose = Counter('-v', help='Increase logging verbosity (can specify multiple times)')

    def _init_command_(self):
        from ds_tools.logging import init_logging

        init_logging(self.verbose, names=None, millis=True, set_levels={'PIL': 30})

    def main(self):
        from music_gui.manager.track_views import TrackInfoView, SongFileView, SelectableSongFileView

        self.patch_and_set_mode()
        try:
            # SongFileView.run_all(album=self.path)
            # TrackInfoView.run_all(album=self.path)
            SelectableSongFileView.run_all(album=self.path)
        except Exception:
            log.critical('Exiting run_gui due to unhandled exception', exc_info=True)
            raise

    def patch_and_set_mode(self):
        # from music.common.prompts import set_ui_mode, UIMode
        from music.files.patches import apply_mutagen_patches

        apply_mutagen_patches()
        # set_ui_mode(UIMode.GUI)


# class Configure(MusicManagerGui, help='Configure registry entries for right-click actions'):
#     dry_run = Flag('-D', help='Print the actions that would be taken instead of taking them')
#
#     def main(self):
#         configure(self.dry_run)
