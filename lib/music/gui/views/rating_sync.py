"""
Sync ratings view

:author: Doug Skrypa
"""

from functools import cached_property
from itertools import chain
from typing import Any

from PySimpleGUI import Text, HorizontalSeparator, Column

from ...files.album import AlbumDir
from ...files.exceptions import InvalidAlbumDir
from ..constants import LoadingSpinner
from ..progress import Spinner
from .base import event_handler, RenderArgs, Event, EventData
from .formatting import AlbumFormatter
from .main import MainView
from .popups.simple import popup_input_invalid
from .popups.path_prompt import get_directory
from .utils import DarkInput as Input

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
        ver = 'new' if self.src_album else 'original'
        old_album = self.src_album or self.dst_album
        prompt = f'Select {ver} version of {old_album.name}' if old_album else 'Select an album'
        if path := get_directory(prompt, no_window=True, initial_folder=self._get_last_dir()):
            try:
                album_dir = AlbumDir(path)
            except InvalidAlbumDir as e:
                popup_input_invalid(str(e), logger=cls.log)  # noqa
            else:
                setattr(self, 'dst_album' if self.src_album else 'src_album', album_dir)

    def get_render_args(self) -> RenderArgs:
        full_layout, kwargs = super().get_render_args()
        ele_binds = {}
        win_w, win_h = self._window_size
        max_h = win_h - 66
        col_w = (win_w - 159) // 2

        with Spinner(LoadingSpinner.blue_dots) as spinner:
            layout = [[]]
            albums, formatters = (self.src_album, self.dst_album), (self.src_formatter, self.dst_formatter)
            for loc, album, formatter in zip(('src', 'dst'), albums, formatters):
                rows = [  # menu = 20px; 46 px from menu to 1st track's horizontal separator
                    [Text('Album Path:'), Input(album.path.as_posix(), disabled=True, size=(150, 1))],
                    [HorizontalSeparator()],  # 46 px from menu to 1st track's horizontal separator
                    *chain.from_iterable(tb.as_sync_rows() for tb in spinner(formatter)),  # 86 px each
                ]
                kwargs = dict(scrollable=True, vertical_scroll_only=True) if (len(album) * 86) > max_h else {}
                layout[0].append(Column(rows, key=f'col::track_data::{loc}', size=(col_w, max_h), **kwargs))

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
