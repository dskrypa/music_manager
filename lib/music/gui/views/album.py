"""
View: Album + track tag values.  Allows editing, after which the view transitions to the diff view.

:author: Doug Skrypa
"""

import logging
from dataclasses import fields
from itertools import chain
from typing import Any

from PySimpleGUI import Text, Input, HorizontalSeparator, Column, Element, Button

from ...files.album import AlbumDir
from ...manager.update import AlbumInfo, TrackInfo
from ..constants import LoadingSpinner
from ..progress import Spinner
from .base import event_handler
from .formatting import AlbumBlock
from .main import MainView

__all__ = ['AlbumView']
log = logging.getLogger(__name__)


class AlbumView(MainView, view_name='album'):
    def __init__(self, album: AlbumDir, album_block: AlbumBlock = None, editing: bool = False):
        super().__init__()
        self.album = album
        self.album_block = album_block or AlbumBlock(self, self.album)
        self.editing = editing

    def get_render_args(self) -> tuple[list[list[Element]], dict[str, Any]]:
        layout, kwargs = super().get_render_args()
        with Spinner(LoadingSpinner.blue_dots) as spinner:
            layout.append([Text('Album Path:'), Input(self.album.path.as_posix(), disabled=True, size=(150, 1))])
            layout.append([HorizontalSeparator()])

            spinner.update()
            bkw = {'size': (18, 1)}
            view_buttons = [Button('Edit', key='edit', **bkw), Button('View All Tags', key='all_tags', **bkw)]
            edit_buttons = [Button('Review & Save Changes', key='save', **bkw), Button('Cancel', key='cancel', **bkw)]
            album_container = Column(
                [
                    [
                        Column([[self.album_block.cover_image]], key='col::album_cover'),
                        Column(self.album_block.get_album_data_rows(self.editing), key='col::album_data'),
                        # TODO: Make bool fields be checkboxes
                    ],
                    [HorizontalSeparator()],
                    [
                        Column([view_buttons], key='col::view_buttons', visible=not self.editing),
                        Column([edit_buttons], key='col::edit_buttons', visible=self.editing),
                    ],
                ],
                vertical_alignment='top',
                element_justification='center',
                key='col::album_container',
            )
            track_rows = list(chain.from_iterable(tb.as_info_rows(self.editing) for tb in spinner(self.album_block)))
            track_data = Column(
                track_rows, key='col::track_data', size=(685, 690), scrollable=True, vertical_scroll_only=True
            )
            layout.append([Column([[album_container, track_data]], key='col::all_data')])

        return layout, kwargs

    @event_handler
    def all_tags(self, event: str, data: dict[str, Any]):
        from .tags import AllTagsView

        return AllTagsView(self.album, self.album_block)

    @event_handler
    def cancel(self, event: str, data: dict[str, Any]):
        self.editing = False
        self.render()

    @event_handler('Edit')  # noqa
    def edit(self, event: str, data: dict[str, Any]):
        if not self.editing:
            self.toggle_editing()

    @event_handler
    def save(self, event: str, data: dict[str, Any]):
        from .diff import AlbumDiffView

        self.toggle_editing()
        info_dict = {}
        track_info_dict = {}
        info_fields = {f.name: f for f in fields(AlbumInfo)} | {f.name: f for f in fields(TrackInfo)}

        for data_key, value in data.items():
            # log.debug(f'Processing {data_key=!r}')
            try:  # val::album::key
                key_type, obj_key = data_key.split('::', 1)
                obj, key = obj_key.rsplit('::', 1)
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
        return AlbumDiffView(self.album, album_info, self.album_block)

    def toggle_editing(self):
        self.editing = not self.editing
        always_ro = {'val::album::mp4'}
        for key, ele in self.window.AllKeysDict.items():
            if isinstance(key, str) and key.startswith('val::') and key not in always_ro:
                ele.update(disabled=not self.editing)

        self.window['col::view_buttons'].update(visible=not self.editing)
        self.window['col::edit_buttons'].update(visible=self.editing)
