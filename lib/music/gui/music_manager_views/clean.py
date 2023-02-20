"""
View: Interface for cleaning undesirable tags and calculating/adding BPM if desired.

:author: Doug Skrypa
"""

import logging
from functools import partial, cached_property
from multiprocessing import Pool
from typing import Optional

from PySimpleGUI import Text, Multiline, Column

from ds_tools.fs.paths import Paths
from ds_tools.logging import init_logging, ENTRY_FMT_DETAILED_PID
from music.common.utils import can_add_bpm
from music.files.album import AlbumDir, iter_albums_or_files
from music.files.track.track import SongFile
from ..base_view import event_handler, Event, EventData, RenderArgs
from ..options import GuiOptions, GuiOptionError, SingleParsingError
from ..popups.simple import popup_ok, popup_input_invalid
from ..progress import ProgressTracker
from ..utils import output_log_handler
from .main import MainView

__all__ = ['CleanView']


class CleanView(MainView, view_name='clean'):
    def __init__(self, album: AlbumDir = None, path: Paths = None, **kwargs):
        if not album and not path:
            raise ValueError('CleanView requires at least 1 of album or path')
        elif album and path:
            raise ValueError('CleanView supports either album or path, not both')
        super().__init__(**kwargs)
        self.album = album
        self.paths = path or album.path

        self.files = set()
        self.no_alb_files = set()
        self.albums = []
        for obj in iter_albums_or_files(self.paths):
            if isinstance(obj, AlbumDir):
                self.albums.append(obj)
                self.files.update(obj)
            else:
                self.no_alb_files.add(obj)
                self.files.add(obj)

        bpm_ok = can_add_bpm()
        self.options = GuiOptions(self, disable_on_parsed=True)
        self.options.add_bool('bpm', 'Add BPM', bpm_ok, disabled=not bpm_ok, tooltip='requires Aubio')
        self.options.add_bool('dry_run', 'Dry Run')
        self.options.add_input('threads', 'BPM Threads', 12, row=1, type=int, size=(5, 1))

        self.prog_tracker: Optional[ProgressTracker] = None
        self.output: Optional[Multiline] = None
        self.file_list: Optional[Multiline] = None

    def get_render_args(self) -> RenderArgs:
        full_layout, kwargs = super().get_render_args()

        win_w, win_h = self._window_size

        file_list_str = '\n'.join(sorted((f.path.as_posix() for f in self.files)))
        self.file_list = Multiline(file_list_str, key='file_list', size=((win_w - 395) // 7, 5), disabled=True)

        file_col = Column([[Text(f'Files ({len(self.files)}):')], [self.file_list]], key='col::file_list')
        total_steps = len(self.files) * (3 if self.options['bpm'] else 2)
        bar_w = (win_w - 159) // 11
        track_text = Text('', size=(bar_w - 12, 1))
        self.prog_tracker = ProgressTracker(total_steps, text=track_text, size=(bar_w, 30), key='progress_bar')
        self.output = Multiline(size=self._output_size(), key='output', autoscroll=True)

        layout = [
            [self.options.as_frame('run_clean'), file_col],
            [self.prog_tracker.bar],
            [Text('Processing:'), track_text],
            [self.output],
        ]
        full_layout.append([self.as_workflow(layout, back_tooltip='Go back to view album')])
        return full_layout, kwargs

    def _output_size(self):
        win_w, win_h = self._window_size
        width, height = ((win_w - 180) // 7, (win_h - 214) // 16)
        return width, height

    @cached_property
    def result_logger(self):
        result_logger = logging.getLogger(f'{self.__class__.__name__}:pool_results')
        result_logger.propagate = False
        return result_logger

    @event_handler('btn::next')
    def run_clean(self, event: Event, data: EventData):
        try:
            self.options.parse(data)
        except GuiOptionError as e:
            if isinstance(e, SingleParsingError) and e.option['name'] == 'threads':
                popup_input_invalid(
                    f'Invalid BPM threads value={e.value!r} (must be an integer) - using 4 instead', logger=self.log
                )
                self.options['threads'] = 4
            else:
                popup_input_invalid(str(e), logger=self.log)
                return self

        self.render()  # to disable inputs

        dry_run = self.options['dry_run']
        rm_tags = self.config.get('rm_tags', None)
        with output_log_handler(self.output, level=0, logger=self.result_logger):
            for album in self.albums:
                album.remove_bad_tags(dry_run, self.prog_tracker.update, extras=rm_tags)
                album.fix_song_tags(dry_run, add_bpm=False, cb=self.prog_tracker.update)

            if self.no_alb_files:
                AlbumDir._remove_bad_tags(self.no_alb_files, dry_run, self.prog_tracker.update, extras=rm_tags)
                AlbumDir._fix_song_tags(self.no_alb_files, dry_run, add_bpm=False, cb=self.prog_tracker.update)

            if self.options['bpm']:
                self.prog_tracker.text.update('Adding BPM...')
                _init_logging = partial(init_logging, 2, log_path=None, names=None, entry_fmt=ENTRY_FMT_DETAILED_PID)
                add_bpm_func = partial(SongFile.maybe_add_bpm, dry_run=dry_run)
                with Pool(self.options['threads'], _init_logging) as pool:
                    for result in self.prog_tracker(pool.imap_unordered(add_bpm_func, list(self.files))):
                        self.result_logger.info(result)

        popup_ok('Finished processing tracks')

    @event_handler
    def window_resized(self, event: Event, data: EventData):
        super().window_resized(event, data)
        width, height = self._output_size()
        self.output.Widget.configure(width=width, height=height)
        self.prog_tracker.bar.Widget.configure(length=(width * 7) + 21)
        # 395: outer=180, options=190, opt_left_border=5, between=20
        self.file_list.Widget.configure(width=(self._window_size[0] - 395) // 7)
