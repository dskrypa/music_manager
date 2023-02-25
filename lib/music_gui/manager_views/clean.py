"""
View: Interface for cleaning undesirable tags and calculating/adding BPM if desired.
"""

from __future__ import annotations

import logging
from functools import partial
from multiprocessing import Pool
from typing import TYPE_CHECKING

from ds_tools.caching.decorators import cached_property
from ds_tools.logging import init_logging, ENTRY_FMT_DETAILED_PID

from tk_gui.elements import Text, Frame, InteractiveFrame, ProgressBar
from tk_gui.elements.buttons import EventButton as EButton
from tk_gui.elements.text import Multiline, gui_log_handler
from tk_gui.event_handling import button_handler
from tk_gui.options import GuiOptions, BoolOption, InputOption
from tk_gui.popups import popup_ok

from music.common.utils import can_add_bpm
from music.files.bulk_actions import remove_bad_tags, fix_song_tags
from music.files.track.track import SongFile, iter_music_files

from music_gui.utils import AlbumIdentifier, get_album_dir
from .base import BaseView

if TYPE_CHECKING:
    from tkinter import Event
    from ds_tools.fs.paths import Paths
    from tk_gui.typing import Layout, XY
    from music.files.album import AlbumDir

__all__ = ['CleanView']
log = logging.getLogger(__name__)
result_logger = logging.getLogger(f'{__name__}:pool_results')
result_logger.propagate = False


class CleanView(BaseView, title='Music Manager - Clean & Add BPM'):
    window_kwargs = BaseView.window_kwargs | {'exit_on_esc': True}
    album: AlbumDir | None = None
    files: list[SongFile]

    progress_bar: ProgressBar
    progress_text: Text
    log_box: Multiline

    def __init__(self, album: AlbumIdentifier = None, path: Paths = None, **kwargs):
        if (not album and not path) or (album and path):
            raise TypeError(f'{self.__class__.__name__} requires an album XOR path')
        super().__init__(**kwargs)
        if album:
            self.album = get_album_dir(album)
            self.files = sorted(self.album)
        else:
            self.files = sorted(iter_music_files(path))

    # region Layout Generation

    @cached_property
    def options(self) -> GuiOptions:
        bpm_ok = can_add_bpm()
        option_layout = [
            [
                BoolOption('bpm', 'Add BPM', bpm_ok, disabled=not bpm_ok, tooltip='requires Aubio'),
                BoolOption('dry_run', 'Dry Run'),
            ],
            [InputOption('threads', 'BPM Threads', 12, type=int, size=(5, 1))],
        ]
        return GuiOptions(option_layout)

    @cached_property
    def options_frame(self) -> InteractiveFrame:
        return self.options.as_frame()

    def get_inner_layout(self) -> Layout:
        monitor = self.window.monitor
        mon_w, mon_h = monitor.width, monitor.height
        char_w, char_h = self.window.style.text_size('M')
        file_list_str = '\n'.join(f.path_str for f in self.files)
        file_list = Multiline(file_list_str, size=(mon_w // char_w, 5), expand=True, read_only=True)
        yield [
            Frame([[self.options_frame], [EButton('Run', key='run_clean')]]),
            Frame([[Text(f'Files ({len(self.files)}):')], [file_list]]),
        ]
        # self.progress_bar = ProgressBar(len(self.files), size=(None, 30), fill_x=True, fill_x_pct=0.89, side='t')
        self.progress_bar = ProgressBar(len(self.files), size=(mon_w, 30), side='t')
        self.progress_text = Text('', size=((mon_w // char_w) - 12, 1))
        self.log_box = Multiline(
            size=(mon_w // char_w, mon_h // char_h), read_only=True, auto_scroll=True, expand=True, fill='both'
        )
        yield [self.progress_bar]
        yield [Text('Processing:'), self.progress_text]
        yield [self.log_box]

    # endregion

    def _update_progress(self, track: SongFile, num: int):
        self.progress_bar.increment()
        self.progress_text.update(track.path_str)

    @button_handler('run_clean')
    def run_clean(self, event: Event = None, key=None):
        options = self.options.parse(self.window.results)
        self.options_frame.disable()
        self.progress_bar.update(0, max_value=len(self.files) * (3 if options['bpm'] else 2))

        dry_run = options['dry_run']
        rm_tags = self.window.config.get('rm_tags', None)

        with gui_log_handler(self.log_box, result_logger, 'music', 'music_gui'):
            remove_bad_tags(self.files, dry_run=dry_run, cb=self._update_progress, extras=rm_tags)
            fix_song_tags(self.files, dry_run=dry_run, add_bpm=False, cb=self._update_progress)
            if options['bpm']:
                self.progress_text.update('Adding BPM...')
                _init_logging = partial(init_logging, 2, log_path=None, names=None, entry_fmt=ENTRY_FMT_DETAILED_PID)
                add_bpm_func = partial(SongFile.maybe_add_bpm, dry_run=dry_run)
                with Pool(self.options['threads'], _init_logging) as pool:
                    for result in self.progress_bar(pool.imap_unordered(add_bpm_func, list(self.files))):
                        result_logger.info(result)

        popup_ok('Finished processing tracks')
