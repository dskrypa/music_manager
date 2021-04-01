"""
Gui Views

:author: Doug Skrypa
"""

import logging
from functools import partial, cached_property
from multiprocessing import Pool
from typing import Any, Optional

from PySimpleGUI import Text, Element, Checkbox, Frame, Submit, Input
from PySimpleGUI import popup_ok

from ds_tools.logging import init_logging, ENTRY_FMT_DETAILED_PID
from ...common.utils import aubio_installed
from ...files.album import AlbumDir
from ...manager.file_update import _add_bpm
from ..prompts import popup_input_invalid
from ..progress import ProgressTracker
from .base import ViewManager, event_handler
from .main import MainView

__all__ = ['CleanView']
log = logging.getLogger(__name__)


class CleanView(MainView, view_name='clean'):
    def __init__(self, mgr: 'ViewManager', album: AlbumDir):
        super().__init__(mgr)
        self.album = album
        bpm_ok = aubio_installed()
        self.defaults = {'bpm': bpm_ok, 'dry_run': False, 'threads': '4'}
        self.disabled = {'bpm': not bpm_ok, 'dry_run': False, 'threads': False}
        self.prog_tracker: Optional[ProgressTracker] = None
        self.data = {}
        self.threads = 4

    @cached_property
    def vals(self):
        return {key: self.data.get(key, default) for key, default in self.defaults.items()}

    def get_render_args(self) -> tuple[list[list[Element]], dict[str, Any]]:
        layout, kwargs = super().get_render_args()
        kvargs = {key: {'key': key, 'disabled': self.disabled[key], 'default': val} for key, val in self.vals.items()}
        del kvargs['threads']['default']
        options_layout = [
            [Checkbox('Add BPM', tooltip='requires Aubio', **kvargs['bpm']), Checkbox('Dry Run', **kvargs['dry_run'])],
            [Text('BPM Threads'), Input(self.vals['threads'], **kvargs['threads'])],
            [Submit(disabled=False, key='run_clean')],
        ]

        try:
            self.threads = int(self.vals['threads'])
        except (ValueError, TypeError):
            self.threads = 4
            popup_input_invalid(
                f'Invalid BPM threads value={self.vals["threads"]} (must be an integer) - using 4 instead'
            )

        n_tracks = len(self.album)
        total_steps = n_tracks * 2 + (n_tracks if self.vals['bpm'] else 0)
        track_text = Text('', size=(100, 1))
        self.prog_tracker = ProgressTracker(total_steps, text=track_text, size=(300, 30))
        layout.append([Frame('options', options_layout)])
        layout.append([self.prog_tracker.bar])
        layout.append([Text('Processing:'), track_text])
        return layout, kwargs

    @event_handler
    def run_clean(self, event: str, data: dict[str, Any]):
        from .album import AlbumView

        self.data = data
        del self.__dict__['vals']
        self.render()

        dry_run = self.vals['dry_run']
        self.album.remove_bad_tags(dry_run, self.prog_tracker.update)
        self.album.fix_song_tags(dry_run, add_bpm=False, callback=self.prog_tracker.update)
        if self.vals['bpm']:
            self.prog_tracker.text.update('Adding BPM...')
            _init_logging = partial(init_logging, 2, log_path=None, names=None, entry_fmt=ENTRY_FMT_DETAILED_PID)
            add_bpm_func = partial(_add_bpm, dry_run=dry_run)
            # Using a list instead of an iterator because pool.map needs to be able to chunk the items
            tracks = [f for f in self.album if f.tag_type != 'flac']
            with Pool(self.threads, _init_logging) as pool:
                for result in self.prog_tracker(pool.imap_unordered(add_bpm_func, tracks)):
                    pass

        popup_ok('Finished processing tracks')
        return AlbumView(self.mgr, self.album)
