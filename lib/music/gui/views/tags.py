"""
View: All tags on each track (as opposed to the album view which only shows common tags once)

:author: Doug Skrypa
"""

import re
from collections import defaultdict

from PySimpleGUI import Text, HorizontalSeparator, Column, Frame, Image, Checkbox

from ...files.album import AlbumDir
from ..constants import LoadingSpinner
from ..elements.inputs import DarkInput as Input
from ..options import GuiOptions
from ..progress import Spinner
from .base import RenderArgs, event_handler, Event, EventData
from .formatting import AlbumFormatter
from .main import MainView
from .popups.simple import popup_ok, popup
from .popups.text import TextPopup
from .utils import split_key, update_color

__all__ = ['AllTagsView']


class AllTagsView(MainView, view_name='all_tags'):
    def __init__(self, album: AlbumDir, album_formatter: AlbumFormatter = None, **kwargs):
        super().__init__(**kwargs)
        self.album = album
        self.album_formatter = album_formatter or AlbumFormatter(self, self.album)
        self.album_formatter.view = self

        self.options = GuiOptions(self, submit='Delete Selected Tags', title=None)
        self.options.add_bool('dry_run', 'Dry Run', default=False)

    def get_render_args(self) -> RenderArgs:
        full_layout, kwargs = super().get_render_args()
        ele_binds = {}
        with Spinner(LoadingSpinner.blue_dots) as spinner:
            layout = [
                [Text('Album Path:'), Input(self.album.path.as_posix(), disabled=True, size=(150, 1))],
                [HorizontalSeparator()],
            ]

            track_rows = []
            for track_block in spinner(self.album_formatter):
                track_layout, track_binds = track_block.as_all_tag_rows(True)
                track_rows.extend(track_layout)
                ele_binds.update(track_binds)

            col_left = Column([[Image(size=(165, 0), pad=(0, 0))]], key='spacer::1', pad=(0, 0))  # image fixes center

            common = dict(pad=(0, 0), justification='center', vertical_alignment='center', expand_y=True, expand_x=True)
            tracks_inner = Column(track_rows, key='col::__tracks_inner__', **common)
            scroll = len(self.album_formatter.track_formatters) > 1
            track_col = Column(
                [[tracks_inner]], key='col::track_data', scrollable=scroll, vertical_scroll_only=True, **common
            )

            options_frame = Frame(None, self.options.layout('delete_tags'), key='frame::options')  # noqa
            options_layout = [[options_frame, Image(data=None, size=(0, self._window_size[1]))]]
            options_col = Column(
                options_layout, key='col::options', justification='center', vertical_alignment='center', pad=(0, 0)
            )

            col_right = Column([[options_col]], key='spacer::2', pad=(0, 0))
            layout.append([col_left, track_col, col_right])

        full_layout.append([self.as_workflow(layout)])
        return full_layout, kwargs, ele_binds

    @event_handler
    def pop_out(self, event: Event, data: EventData):
        key, event = event.rsplit(':::', 1)
        path = split_key(key)[1]  # Tag should always be lyrics
        if path.endswith('::USLT'):  # MP3 USLT may be formatted as `USLT::eng` to indicate language
            path = path[:-6]
        track = self.album_formatter.track_formatters[path].track
        lyrics = track.get_tag_value_or_values('lyrics')
        title = f'Lyrics: {track.tag_artist} - {track.tag_album} - {track.tag_title}'
        TextPopup(lyrics, title, multiline=True, auto_size=True, font=('sans-serif', 14)).get_result()

    @event_handler('del::*')
    def row_clicked(self, event: Event, data: EventData):
        try:
            key, event = event.rsplit(':::', 1)
        except ValueError:  # Checkbox was clicked - toggle already happened
            key = event
        else:               # Input was clicked - need to toggle checkbox
            check_box, to_be_deleted = self._get_check_box(key, True)
            check_box.update(to_be_deleted)

        self._update_color(key)

    def _get_check_box(self, key: str, inverse: bool = False) -> tuple[Checkbox, bool]:
        if key.startswith('val::'):
            key = f'del{key[3:]}'

        box = self.window.key_dict[key]  # type: Checkbox  # noqa
        to_be_deleted = bool(box.TKIntVar.get())
        return box, (not to_be_deleted) if inverse else to_be_deleted

    def _update_color(self, key: str):
        to_be_deleted = self._get_check_box(key)[1]
        if key.startswith('del::'):
            key = f'val{key[3:]}'
        input_ele = self.window[key]
        if to_be_deleted:
            bg, fg = '#781F1F', '#FFFFFF'
        else:
            bg = getattr(input_ele, 'disabled_readonly_background_color', input_ele.BackgroundColor)
            fg = getattr(input_ele, 'disabled_readonly_text_color', input_ele.TextColor)

        update_color(input_ele, fg, bg)

    @event_handler
    def tag_clicked(self, event: Event, data: EventData):
        key, event = event.rsplit(':::', 1)
        tag = split_key(key)[2]

        row_box, to_be_deleted = self._get_check_box(key, True)
        for tb in self.album_formatter:
            track_key = f'val::{tb.path_str}::{tag}'
            if track_key in self.window.key_dict:
                track_box, track_tbd = self._get_check_box(track_key)
                if track_tbd != to_be_deleted:
                    track_box.update(to_be_deleted)
                    self._update_color(track_key)

    @event_handler('btn::next')
    def delete_tags(self, event: Event, data: EventData):
        self.options.parse(data)
        dry_run = self.options['dry_run']
        prefix = '[DRY RUN] Would delete' if dry_run else 'Deleting'

        multi_value_match = re.compile(r'^(.*?)--\d+$').match
        prompted = set()
        to_delete = defaultdict(set)
        for data_key, value in data.items():
            if key_parts := split_key(data_key):
                key_type, path, tag_id = key_parts
                if key_type == 'del' and value:
                    if m := multi_value_match(tag_id):
                        tag_id = m.group(1)
                        if tag_id not in prompted:
                            prompted.add(tag_id)
                            msg = f'Found multiple tags for file with {tag_id=}. Continue with delete?'
                            if not popup(msg, 'Warning', button_text={'Cancel': False, 'Yes, delete all': True}):
                                return

                    to_delete[path].add(tag_id)

        if not to_delete:
            return popup_ok('No tags were selected for deletion')

        for path, tags in sorted(to_delete.items()):
            track = self.album[path]
            tag_str = ', '.join(sorted(tags))
            self.log.info(f'{prefix} {len(tags)} tags from {track.path.name}: {tag_str}')
            if not dry_run:
                track.remove_tags(tags)

        if not dry_run:
            self.album_formatter = AlbumFormatter(self, self.album)  # Reset cached info
            self.render()

    @event_handler('btn::back')
    def back(self, event: Event, data: EventData):
        from .album import AlbumView

        if (last := self.last_view) is not None:
            return last.__class__(album=self.album, album_formatter=self.album_formatter, last_view=self)
        return AlbumView(self.album, self.album_formatter, last_view=self)
