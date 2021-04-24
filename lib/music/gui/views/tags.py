"""
View: All tags on each track (as opposed to the album view which only shows common tags once)

:author: Doug Skrypa
"""

from PySimpleGUI import Text, HorizontalSeparator, Column, Listbox

from ...files.album import AlbumDir
from ..constants import LoadingSpinner
from ..progress import Spinner
from .base import RenderArgs, event_handler, Event, EventData
from .formatting import AlbumBlock
from .main import MainView
from .utils import DarkInput as Input

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
                track_layout, track_binds = track_block.as_all_tag_rows(True)
                track_rows.extend(track_layout)
                ele_binds.update(track_binds)

            common = dict(pad=(0, 0), justification='center', vertical_alignment='center')
            tracks_inner = Column(track_rows, key='col::__tracks_inner__', expand_y=True, expand_x=True, **common)
            track_col = Column(
                [[tracks_inner]], key='col::track_data', scrollable=True, vertical_scroll_only=True, **common
            )
            layout.append([Column([], key='spacer::1', pad=(0, 0)), track_col, Column([], key='spacer::2', pad=(0, 0))])

        return layout, kwargs, ele_binds

    @event_handler('del::*')
    def row_clicked(self, event: Event, data: EventData):
        try:
            key, event = event.rsplit(':::', 1)
        except ValueError:
            check_box_key, key = event, f'val{event[3:]}'
            check_box = self.window[check_box_key]
            to_be_deleted = check_box.TKIntVar.get()
        else:
            check_box_key = f'del{key[3:]}'
            check_box = self.window[check_box_key]
            to_be_deleted = not check_box.TKIntVar.get()
            check_box.update(to_be_deleted)

        input_ele = self.window[key]
        if to_be_deleted:
            bg, fg = '#781F1F', '#FFFFFF'
        else:
            bg = getattr(input_ele, 'disabled_readonly_background_color', input_ele.BackgroundColor)
            fg = getattr(input_ele, 'disabled_readonly_text_color', input_ele.TextColor)

        if isinstance(input_ele, Input):
            input_ele.update(background_color=bg, text_color=fg)
        elif isinstance(input_ele, Listbox):
            input_ele.TKListbox.configure(bg=bg, fg=fg)
