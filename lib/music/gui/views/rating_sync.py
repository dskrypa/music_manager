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
from ..base_view import event_handler, RenderArgs, Event, EventData
from ..constants import LoadingSpinner
from ..elements.inputs import DarkInput as Input
from ..progress import Spinner
from .formatting import AlbumFormatter
from .main import MainView
from .popups.simple import popup_input_invalid
from .popups.path_prompt import get_directory
from .popups.text import popup_ok

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
        dir_type = 'sync_dst' if self.src_album else 'sync_src'
        last_dir = self._get_last_dir(dir_type)
        if path := get_directory(prompt, no_window=True, initial_folder=last_dir):
            try:
                album_dir = AlbumDir(path)
            except InvalidAlbumDir as e:
                popup_input_invalid(str(e), logger=cls.log)  # noqa
            else:
                if path != last_dir:
                    self.state[f'last_dir:{dir_type}'] = path.as_posix()
                    self.state.save()
                setattr(self, 'dst_album' if self.src_album else 'src_album', album_dir)
                return True
        return False

    def get_render_args(self) -> RenderArgs:
        full_layout, kwargs = super().get_render_args()
        ele_binds = {}
        win_w, win_h = self._window_size
        max_h = win_h - 66

        with Spinner(LoadingSpinner.blue_dots) as spinner:
            layout = [[]]
            albums, formatters = (self.src_album, self.dst_album), (self.src_formatter, self.dst_formatter)
            for loc, album, formatter in zip(('src', 'dst'), albums, formatters):
                path_key = f'path::{loc}'
                path = Input(
                    album.path.as_posix(), key=path_key, disabled=True, size=(150, 1), tooltip='Click to change album'
                )
                ele_binds[path_key] = {'<Button-1>': ':::album_clicked'}
                rows = [  # menu = 20px; 46 px from menu to 1st track's horizontal separator
                    [Text('Album Path:'), path],
                    [HorizontalSeparator()],
                    *chain.from_iterable(tb.as_sync_rows() for tb in spinner(formatter)),  # 86 px each
                ]
                col_w = (win_w - 159) // 2
                if (len(album) * 86) > max_h:
                    col_kwargs = dict(scrollable=True, vertical_scroll_only=True)
                    col_w -= 17
                else:
                    col_kwargs = {}

                layout[0].append(Column(rows, key=f'col::track_data::{loc}', size=(col_w, max_h), **col_kwargs))

        workflow = self.as_workflow(layout, back_tooltip='Cancel Changes', next_tooltip='Review & Save Changes')
        full_layout.append(workflow)

        return full_layout, kwargs, ele_binds

    @event_handler
    def album_clicked(self, event: Event, data: EventData):
        loc = event.split('::')[1]
        attr = f'{loc}_album'
        original = getattr(self, attr)
        setattr(self, attr, None)
        if not self._get_album():
            popup_ok(f'Keeping previous {attr}={original!r}')
            setattr(self, attr, original)
        else:
            del self.__dict__[f'{loc}_formatter']
            self.render()

    def _back_kwargs(self, last: 'MainView') -> dict[str, Any]:
        if last.name == 'album':
            return {'album': last.album}  # noqa
        return {}

    @event_handler('btn::next')
    def save(self, event: Event, data: EventData):
        from .diff import AlbumDiffView

        src_info = self.src_formatter.album_info
        new_info = self.dst_formatter.album_info.copy()

        for src_track, dst_track in zip(src_info.tracks.values(), new_info.tracks.values()):
            dst_track.rating = src_track.rating

        options = {'no_album_move': True, 'add_genre': False}
        return AlbumDiffView(self.dst_album, new_info, self.dst_formatter, last_view=self, options=options)
