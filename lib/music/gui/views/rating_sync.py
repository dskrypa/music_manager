"""
Sync ratings view

:author: Doug Skrypa
"""

from functools import cached_property
from itertools import chain
from pathlib import Path
from typing import Any

from PySimpleGUI import Text, HorizontalSeparator, Column, Button

from ...files.album import AlbumDir
from ...files.exceptions import InvalidAlbumDir
from ...files.track.utils import stars_to_256
from ...manager.update import AlbumInfo, TrackInfo
from ..constants import LoadingSpinner
from ..progress import Spinner
from .base import event_handler, RenderArgs, Event, EventData
from .formatting import AlbumFormatter
from .main import MainView
from .popups.simple import popup_ok, popup_input_invalid
from .popups.text import popup_error
from .popups.path_prompt import get_directory
from .utils import split_key, DarkInput as Input

__all__ = ['SyncRatingsView']


class SyncRatingsView(MainView, view_name='sync_ratings'):
    def __init__(self, src_album: AlbumDir = None, dst_album: AlbumDir = None, **kwargs):
        super().__init__(**kwargs)
        self.src_album = src_album
        self.dst_album = dst_album
        n = sum(1 for album in (src_album, dst_album) if album)
        while (self.src_album is None or self.dst_album is None) and n < 2:
            self._get_album()
            n += 1

        if self.src_album is None or self.dst_album is None:
            raise ValueError('A source and destination album are both required')

    @cached_property
    def src_formatter(self) -> AlbumFormatter:
        return AlbumFormatter(self, self.src_album)

    @cached_property
    def dst_formatter(self) -> AlbumFormatter:
        return AlbumFormatter(self, self.dst_album)

    def _get_album(self):
        if self.src_album:
            prompt = f'Select new version of {self.src_album.name}'
        elif self.dst_album:
            prompt = f'Select original version of {self.dst_album.name}'
        else:
            prompt = 'Select an album'

        last_dir = self._get_last_dir()
        if path := get_directory(prompt, no_window=True, initial_folder=last_dir):
            try:
                album_dir = AlbumDir(path)
            except InvalidAlbumDir as e:
                popup_input_invalid(str(e), logger=cls.log)  # noqa
            else:
                if self.src_album:
                    self.dst_album = album_dir
                else:
                    self.src_album = album_dir

    def get_render_args(self) -> RenderArgs:
        full_layout, kwargs = super().get_render_args()
        ele_binds = {}

        with Spinner(LoadingSpinner.blue_dots) as spinner:
            layout = []

            row = []
            keys = {'title', 'num', 'rating'}
            albums = (self.src_album, self.dst_album)
            formatters = (self.src_formatter, self.dst_formatter)

            for loc, album, formatter in zip(('src', 'dst'), albums, formatters):
                rows = [
                    [Text('Album Path:'), Input(album.path.as_posix(), disabled=True, size=(150, 1))],
                    [HorizontalSeparator()],
                    *chain.from_iterable(tb.as_info_rows(False, keys) for tb in spinner(formatter)),
                ]
                track_data = Column(
                    rows, key=f'col::track_data::{loc}', size=(685, 690), scrollable=True, vertical_scroll_only=True
                )
                row.append(track_data)

            layout.append(row)

        workflow = self.as_workflow(layout, back_tooltip='Cancel Changes', next_tooltip='Review & Save Changes')
        full_layout.append(workflow)

        return full_layout, kwargs, ele_binds

    def _back_kwargs(self, last: 'MainView') -> dict[str, Any]:
        if last.name == 'album':
            return {'album': last.album}  # noqa
        return {}

    @event_handler('btn::next')
    def save(self, event: Event, data: EventData):
        pass
