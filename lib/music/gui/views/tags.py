"""
View: All tags on each track (as opposed to the album view which only shows common tags once)

:author: Doug Skrypa
"""

from PySimpleGUI import Text, Input, HorizontalSeparator, Column

from ...files.album import AlbumDir
from ..constants import LoadingSpinner
from ..progress import Spinner
from .base import RenderArgs
from .formatting import AlbumBlock
from .main import MainView

__all__ = ['AllTagsView']


class AllTagsView(MainView, view_name='all_tags'):
    def __init__(self, album: AlbumDir, album_block: AlbumBlock = None, **kwargs):
        super().__init__(**kwargs)
        self.album = album
        self.album_block = album_block or AlbumBlock(self, self.album)
        self.album_block.view = self

    def get_render_args(self) -> RenderArgs:
        layout, kwargs = super().get_render_args()
        ele_binds = {}
        with Spinner(LoadingSpinner.blue_dots) as spinner:
            layout.append([Text('Album Path:'), Input(self.album.path.as_posix(), disabled=True, size=(150, 1))])
            layout.append([HorizontalSeparator()])

            track_rows = []
            for track_block in spinner(self.album_block):
                track_layout, track_binds = track_block.as_all_tag_rows(False)
                track_rows.extend(track_layout)
                ele_binds.update(track_binds)

            common = dict(pad=(0, 0), justification='center', vertical_alignment='center')
            tracks_inner = Column(track_rows, key='col::__tracks_inner__', expand_y=True, expand_x=True, **common)
            track_col = Column(
                [[tracks_inner]], key='col::track_data', scrollable=True, vertical_scroll_only=True, **common
            )
            layout.append([Column([], key='spacer::1', pad=(0, 0)), track_col, Column([], key='spacer::2', pad=(0, 0))])

        return layout, kwargs, ele_binds
