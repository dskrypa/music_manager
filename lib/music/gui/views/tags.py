"""
View: All tags on each track (as opposed to the album view which only shows common tags once)

:author: Doug Skrypa
"""

from itertools import chain
from typing import Any

from PySimpleGUI import Text, Input, HorizontalSeparator, Column, Element

from ...files.album import AlbumDir
from ..constants import LoadingSpinner
from ..progress import Spinner
from .base import event_handler
from .formatting import AlbumBlock, split_key
from .main import MainView

__all__ = ['AllTagsView']


class AllTagsView(MainView, view_name='all_tags'):
    def __init__(self, album: AlbumDir, album_block: AlbumBlock = None, **kwargs):
        super().__init__(**kwargs)
        self.album = album
        self.album_block = album_block or AlbumBlock(self, self.album)
        self.album_block.view = self

    def get_render_args(self) -> tuple[list[list[Element]], dict[str, Any]]:
        layout, kwargs = super().get_render_args()

        with Spinner(LoadingSpinner.blue_dots) as spinner:
            layout.append([Text('Album Path:'), Input(self.album.path.as_posix(), disabled=True, size=(150, 1))])
            layout.append([HorizontalSeparator()])

            track_rows = list(chain.from_iterable(tb.as_all_tag_rows(False) for tb in spinner(self.album_block)))
            size = tuple(v - 20 for v in self._window_size)
            # noinspection PyTypeChecker
            track_col = Column(track_rows, key='col::track_data', size=size, scrollable=True, vertical_scroll_only=True)
            layout.append([track_col])

        return layout, kwargs

    def handle_event(self, event: str, data: dict[str, Any]):
        if event.startswith('img::'):
            data['image_key'] = event
            event = 'image_clicked'

        return super().handle_event(event, data)

    @event_handler
    def image_clicked(self, event: str, data: dict[str, Any]):
        from .popups.image import ImageView

        image_key = data['image_key']
        track_path = split_key(image_key)[1]
        track_block = self.album_block.track_blocks[track_path]
        return ImageView(track_block.cover_image_obj, f'Track Album Cover: {track_block.file_name}')
