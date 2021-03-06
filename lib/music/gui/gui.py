"""
Music manager GUI using PySimpleGUI.  WIP.

:author: Doug Skrypa
"""

import logging
from pathlib import Path
from functools import partial
from multiprocessing import Pool
from typing import Dict, Any, Optional, Union, List

from PySimpleGUI import Text, Button, Column, HorizontalSeparator, Element, Menu, Checkbox, ProgressBar, Frame, Submit
from PySimpleGUI import Input
from PySimpleGUI import popup_ok, theme

from ds_tools.logging import init_logging, ENTRY_FMT_DETAILED_PID
from ..common.utils import aubio_installed
from ..files.album import AlbumDir
from ..files.track.track import SongFile
from ..manager.file_update import _add_bpm
from .base import GuiBase, event_handler, view
from .formatting import get_track_data, get_cover_image
from .prompts import directory_prompt

__all__ = ['MusicManagerGui']
log = logging.getLogger(__name__)


class MusicManagerGui(GuiBase):
    def __init__(self):
        theme('SystemDefaultForReal')
        super().__init__(title='Music Manager', resizable=True, size=(800, 500))
        self.menu = [
            ['File', ['Open', 'Exit']],
            ['Actions', ['Clean', 'Wiki Update']],
            ['Help', ['About']],
        ]
        self.show_view('main')

    def set_layout(self, layout: List[List[Element]], **kwargs):
        # noinspection PyTypeChecker
        return super().set_layout([[Menu(self.menu)]] + layout, **kwargs)

    @view('main')
    def main(self, rows=None):
        self.set_layout(rows or [[Button('Select Album', enable_events=True, key='select_album')]])

    def _select_album_path(self):
        if path := directory_prompt('Select Album'):
            log.debug(f'Selected album {path=}')
            self.state['album'] = AlbumDir(path)
        else:
            self.state['album'] = None

    @property
    def album(self) -> Optional[AlbumDir]:
        if self.state.get('album') is None:
            self._select_album_path()
        return self.state['album']

    @album.setter
    def album(self, path: Union[str, Path]):
        self.state['album'] = AlbumDir(path)

    @event_handler('select_album', 'Open')
    @view('tracks')
    def show_tracks(self, event: Optional[str] = None, data: Optional[Dict[str, Any]] = None):
        if event is None:
            album = self.album
        else:
            self.window.hide()
            self._select_album_path()
            if not (album := self.album):
                self.window.un_hide()
                self.main([[Text('No album selected.')]])
                return

        bar = ProgressBar(len(album), size=(300, 30))
        self.set_layout([[Text(f'Album: {album.path}', key='album_path')], [Text('Loading...')], [bar]])

        track_rows = []
        for i, track in enumerate(album, 1):
            track_rows.append([HorizontalSeparator()])
            track_rows.append([Text(f'{track.path.as_posix()} [{track.length_str}] ({track.tag_version})')])
            track_rows.append([Column([[get_cover_image(track)]]), Column(get_track_data(track))])
            bar.update(i)

        rows = [
            [Text(f'Album: {album.path}')],
            [Column(track_rows, scrollable=True, size=(800, 500))]  # window.extend_layout doesn't work with scrollable
        ]
        self.set_layout(rows)

    @event_handler('window_resized')
    def window_resized(self, event: str, data: Dict[str, Any]):
        log.debug(f'Window size changed from {data["old_size"]} to {data["new_size"]}')
        if self.state.get('view') == 'tracks':
            log.debug(f'Expanding columns on {self.window}')
            expand_columns(self.window.Rows)

    @event_handler('Clean', 'run_clean')
    @view('clean')
    def clean_tracks(self, event: str, data: Dict[str, Any]):
        bpm_ok = aubio_installed()
        run_clean = event == 'run_clean'
        disabled = {'bpm': run_clean or not bpm_ok, 'dry_run': run_clean, 'threads': run_clean}
        values = {
            'bpm': data.get('add_bpm', bpm_ok),
            'dry_run': data.get('dry_run', False),
            'threads': data.get('threads', '4'),
        }
        options_layout = [
            [
                Checkbox(
                    'Add BPM', default=values['bpm'], disabled=disabled['bpm'], tooltip='requires Aubio', key='add_bpm'
                ),
                Checkbox('Dry Run', default=values['dry_run'], disabled=disabled['dry_run'], key='dry_run'),
            ],
            [
                Text('BPM Threads'), Input(values['threads'], disabled=disabled['threads'], key='threads'),
            ],
            [Submit(disabled=run_clean, key='run_clean')],
        ]

        log.debug(f'Cleaning tracks with {values=}')

        try:
            threads = int(values['threads'])
        except (ValueError, TypeError):
            threads = 4
            popup_ok(f'Invalid BPM threads value={values["threads"]} (must be an integer) - using 4 instead')

        n_tracks = len(self.album)
        bar = ProgressBar(n_tracks * 2 + (n_tracks if values['bpm'] else 0), size=(300, 30))
        track_text = Text('', size=(100, 1))
        layout = [
            [Frame('options', options_layout)],
            [bar],
            [Text('Processing:'), track_text],
        ]
        self.set_layout(layout)
        if not run_clean:
            return

        complete = 0

        def update_progress(track: SongFile, n: int):
            nonlocal complete
            track_text.update(track.path.as_posix())
            complete += 1
            bar.update(complete)

        dry_run = values['dry_run']
        self.album.remove_bad_tags(dry_run, update_progress)
        self.album.fix_song_tags(dry_run, add_bpm=False, callback=update_progress)
        if values['bpm']:
            track_text.update('Adding BPM...')
            _init_logging = partial(init_logging, 2, log_path=None, names=None, entry_fmt=ENTRY_FMT_DETAILED_PID)
            add_bpm_func = partial(_add_bpm, dry_run=dry_run)
            # Using a list instead of an iterator because pool.map needs to be able to chunk the items
            tracks = [f for f in self.album if f.tag_type != 'flac']
            with Pool(threads, _init_logging) as pool:
                for result in pool.imap_unordered(add_bpm_func, tracks):
                    complete += 1
                    bar.update(complete)

        popup_ok('Finished processing tracks')
        self.show_view('tracks')


def expand_columns(rows: List[List[Element]]):
    for row in rows:
        for ele in row:
            if isinstance(ele, Column):
                ele.expand(True, True)
            try:
                ele_rows = ele.Rows
            except AttributeError:
                pass
            else:
                log.debug(f'Expanding columns on {ele}')
                expand_columns(ele_rows)
