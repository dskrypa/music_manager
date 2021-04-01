"""
Music manager GUI using PySimpleGUI.  WIP.

Notes:
    - window.extend_layout doesn't work with a scrollable Column

:author: Doug Skrypa
"""

import logging
from dataclasses import fields
from pathlib import Path
from functools import partial
from multiprocessing import Pool
from typing import Any, Optional, Union

from PySimpleGUI import Text, Button, Column, Element, Checkbox, Frame, Submit, Input
from PySimpleGUI import popup_ok, theme

from ds_tools.logging import init_logging, ENTRY_FMT_DETAILED_PID
from ..common.utils import aubio_installed
from ..files.album import AlbumDir
from ..files.exceptions import InvalidAlbumDir
from ..manager.file_update import _add_bpm
from ..manager.update import AlbumInfo, TrackInfo
from .base import GuiBase, event_handler, view
from .formatting import AlbumBlock
from .prompts import directory_prompt, popup_input_invalid
from .progress import ProgressTracker

__all__ = ['MusicManagerGui']
log = logging.getLogger(__name__)


class MusicManagerGui(GuiBase):
    def __init__(self):
        theme('SystemDefaultForReal')
        super().__init__(title='Music Manager', resizable=True, size=(1500, 750))
        self.menu = [
            ['File', ['Open', 'Exit']],
            ['Actions', ['Clean', 'Edit', 'Wiki Update']],
            ['Help', ['About']],
        ]
        self.show_view('main')
        self.album = None
        self.album_block = None

    @event_handler('window_resized')
    def window_resized(self, event: str, data: dict[str, Any]):
        log.debug(f'Window size changed from {data["old_size"]} to {data["new_size"]}')
        if self.state.get('view') == 'tracks':
            log.debug(f'Expanding columns on {self.window}')
            expand_columns(self.window.Rows)

    @view('main')
    def main(self, rows=None):
        self.set_layout(rows or [[Button('Select Album', enable_events=True, key='select_album')]])

    @property
    def album(self) -> Optional[AlbumDir]:
        if self._album is None:
            if path := directory_prompt('Select Album'):
                log.debug(f'Selected album {path=}')
                self.album = path
        return self._album

    @album.setter
    def album(self, path: Union[str, Path, None, AlbumDir]):
        try:
            self._album = AlbumDir(path) if isinstance(path, (str, Path)) else path
        except InvalidAlbumDir as e:
            popup_input_invalid(str(e))

    @event_handler('select_album', 'Open', 'album::all_tags', 'album::cancel')
    def show_tracks(self, event: Optional[str] = None, data: Optional[dict[str, Any]] = None):
        if event == 'Open':
            self.album = None
        if not self.album:
            self.main([[Text('No album selected.')]])
            return

        if event == 'album::all_tags':
            self._all_tags()
        else:
            self._album_and_tracks()

    @view('album_and_tracks')
    def _album_and_tracks(self):
        self.album_block = AlbumBlock(self, self.album)
        self.set_layout(list(self.album_block.as_rows(False)))

    @view('all_tags')
    def _all_tags(self):
        self.album_block = AlbumBlock(self, self.album)
        self.set_layout(list(self.album_block.as_tag_rows()))

    @event_handler('Edit', 'album::edit')
    def edit_tracks(self, event: str, data: dict[str, Any]):
        if not self.album:
            self.main([[Text('No album selected.')]])
            return

        if self.state['view'] != 'album_and_tracks':
            self._album_and_tracks()
        if not self.album_block.editing:  # Needs to be separate so this will trigger when the above is true
            self.album_block.toggle_editing()

    @event_handler('album::save')
    def review_changes(self, event: str, data: dict[str, Any]):
        self.album_block.toggle_editing()
        info_dict = {}
        track_info_dict = {}
        info_fields = {f.name: f for f in fields(AlbumInfo)} | {f.name: f for f in fields(TrackInfo)}

        for data_key, value in data.items():
            try:
                key_type, obj, key = data_key.split('::')  # val::album::key
            except Exception:
                pass
            else:
                if key_type == 'val':
                    try:
                        value = info_fields[key].type(value)
                    except (KeyError, TypeError, ValueError):
                        pass
                    if obj == 'album':
                        info_dict[key] = value
                    else:
                        track_info_dict.setdefault(obj, {})[key] = value
        info_dict['tracks'] = track_info_dict

        album_info = AlbumInfo.from_dict(info_dict)
        # TODO: Make dry_run not default
        # TODO: Implement gui-based diff
        # TODO: Input sanitization/normalization
        album_info.update_and_move(self.album, None, dry_run=True)

    @event_handler('Wiki Update')
    @view('wiki_update')
    def wiki_update(self, event: str, data: dict[str, Any]):
        popup_ok('Wiki update is not implemented yet.')

    @event_handler('Clean', 'run_clean')
    @view('clean_tracks')
    def clean_tracks(self, event: str, data: dict[str, Any]):
        bpm_ok = aubio_installed()
        run_clean = event == 'run_clean'
        defaults = {'bpm': bpm_ok, 'dry_run': False, 'threads': '4'}
        vals = {key: data.get(key, default) for key, default in defaults.items()}
        disabled = {'bpm': run_clean or not bpm_ok, 'dry_run': run_clean, 'threads': run_clean}
        kwargs = {key: {'key': key, 'disabled': disabled[key], 'default': val} for key, val in vals.items()}
        del kwargs['threads']['default']

        options_layout = [
            [Checkbox('Add BPM', tooltip='requires Aubio', **kwargs['bpm']), Checkbox('Dry Run', **kwargs['dry_run'])],
            [Text('BPM Threads'), Input(vals['threads'], **kwargs['threads'])],
            [Submit(disabled=run_clean, key='run_clean')],
        ]
        log.debug(f'Cleaning tracks with {vals=}')

        try:
            threads = int(vals['threads'])
        except (ValueError, TypeError):
            threads = 4
            popup_input_invalid(f'Invalid BPM threads value={vals["threads"]} (must be an integer) - using 4 instead')

        n_tracks = len(self.album)
        total_steps = n_tracks * 2 + (n_tracks if vals['bpm'] else 0)
        track_text = Text('', size=(100, 1))
        prog_tracker = ProgressTracker(total_steps, text=track_text, size=(300, 30))
        layout = [
            [Frame('options', options_layout)],
            [prog_tracker.bar],
            [Text('Processing:'), track_text],
        ]
        self.set_layout(layout)
        if not run_clean:
            return

        dry_run = vals['dry_run']
        self.album.remove_bad_tags(dry_run, prog_tracker.update)
        self.album.fix_song_tags(dry_run, add_bpm=False, callback=prog_tracker.update)
        if vals['bpm']:
            track_text.update('Adding BPM...')
            _init_logging = partial(init_logging, 2, log_path=None, names=None, entry_fmt=ENTRY_FMT_DETAILED_PID)
            add_bpm_func = partial(_add_bpm, dry_run=dry_run)
            # Using a list instead of an iterator because pool.map needs to be able to chunk the items
            tracks = [f for f in self.album if f.tag_type != 'flac']
            with Pool(threads, _init_logging) as pool:
                for result in prog_tracker(pool.imap_unordered(add_bpm_func, tracks)):
                    pass

        popup_ok('Finished processing tracks')
        self.show_view('album_and_tracks')


def expand_columns(rows: list[list[Element]]):
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
