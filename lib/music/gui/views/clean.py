"""
View: Interface for cleaning undesirable tags and calculating/adding BPM if desired.

:author: Doug Skrypa
"""

import logging
from functools import partial
from multiprocessing import Pool
from typing import Any, Optional

from PySimpleGUI import Text, Element
from PySimpleGUI import popup_ok

from ds_tools.logging import init_logging, ENTRY_FMT_DETAILED_PID
from ...common.utils import aubio_installed
from ...files.album import AlbumDir
from ...manager.file_update import _add_bpm
from ..options import GuiOptions, GuiOptionError, SingleParsingError
from ..progress import ProgressTracker
from ..prompts import popup_input_invalid
from .base import ViewManager, event_handler
from .main import MainView

__all__ = ['CleanView']
log = logging.getLogger(__name__)


class CleanView(MainView, view_name='clean'):
    def __init__(self, mgr: 'ViewManager', album: AlbumDir):
        super().__init__(mgr)
        self.album = album
        bpm_ok = aubio_installed()
        self.options = GuiOptions(self, disable_on_parsed=True)
        self.options.add_bool('bpm', 'Add BPM', bpm_ok, disabled=not bpm_ok, tooltip='requires Aubio')
        self.options.add_bool('dry_run', 'Dry Run')
        self.options.add_input('threads', 'BPM Threads', 4, row=1, type=int)
        self.prog_tracker: Optional[ProgressTracker] = None

    def get_render_args(self) -> tuple[list[list[Element]], dict[str, Any]]:
        layout, kwargs = super().get_render_args()
        layout.append([self.options.as_frame('run_clean')])
        n_tracks = len(self.album)
        total_steps = n_tracks * 2 + (n_tracks if self.options['bpm'] else 0)
        track_text = Text('', size=(100, 1))
        self.prog_tracker = ProgressTracker(total_steps, text=track_text, size=(300, 30))
        layout.append([self.prog_tracker.bar])
        layout.append([Text('Processing:'), track_text])
        return layout, kwargs

    @event_handler
    def run_clean(self, event: str, data: dict[str, Any]):
        from .album import AlbumView

        try:
            self.options.parse(data)
        except GuiOptionError as e:
            if isinstance(e, SingleParsingError) and e.option['name'] == 'threads':
                popup_input_invalid(f'Invalid BPM threads value={e.value!r} (must be an integer) - using 4 instead')
                self.options['threads'] = 4
            else:
                popup_input_invalid(e)
                return self

        self.render()  # to disable inputs

        dry_run = self.options['dry_run']
        self.album.remove_bad_tags(dry_run, self.prog_tracker.update)
        self.album.fix_song_tags(dry_run, add_bpm=False, callback=self.prog_tracker.update)
        if self.options['bpm']:
            self.prog_tracker.text.update('Adding BPM...')
            _init_logging = partial(init_logging, 2, log_path=None, names=None, entry_fmt=ENTRY_FMT_DETAILED_PID)
            add_bpm_func = partial(_add_bpm, dry_run=dry_run)
            # Using a list instead of an iterator because pool.map needs to be able to chunk the items
            tracks = [f for f in self.album if f.tag_type != 'flac']
            with Pool(self.options['threads'], _init_logging) as pool:
                for result in self.prog_tracker(pool.imap_unordered(add_bpm_func, tracks)):
                    pass

        popup_ok('Finished processing tracks')
        return AlbumView(self.mgr, self.album)
