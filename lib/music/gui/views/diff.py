"""
View: Diff between original and modified tag values.  Used for both manual and Wiki-based updates.

:author: Doug Skrypa
"""

import logging
from functools import cached_property
from io import BytesIO
from typing import Any, Optional

from PySimpleGUI import Text, Input, Image, HorizontalSeparator, Column, Element

from ...files.album import AlbumDir
from ...files.track.track import SongFile
from ...manager.update import AlbumInfo, TrackInfo
from ..options import GuiOptions, GuiOptionError
from .base import event_handler
from .formatting import AlbumBlock
from .main import MainView
from .utils import get_a_to_b

__all__ = ['AlbumDiffView']
log = logging.getLogger(__name__)


class AlbumDiffView(MainView, view_name='album_diff'):
    def __init__(self, album: AlbumDir, album_info: AlbumInfo, album_block: AlbumBlock = None):
        super().__init__()
        self.album = album
        self.album_info = album_info
        self.album_block = album_block or AlbumBlock(self, self.album)

        self.options = GuiOptions(self, disable_on_parsed=False)
        self.options.add_bool('dry_run', 'Dry Run')
        self.options.add_bool('add_genre', 'Add Genre', kwargs={'change_submits': True})
        self.options.add_bool('title_case', 'Title Case', kwargs={'change_submits': True})

    @cached_property
    def file_info_map(self):
        return self.album_info.get_file_info_map(self.album)

    @cached_property
    def file_tag_map(self):
        return {file: info.tags() for file, info in self.file_info_map.items()}

    @cached_property
    def cover_images(self) -> tuple[Optional[bytes], Optional[bytes]]:
        if self.album_info.cover_path:
            file_img = self.album_info.get_current_cover(self.file_info_map)
            image, img_data = self.album_info.get_new_cover(self.album, file_img)
            if img_data is not None:
                bio = BytesIO()
                file_img.save(bio, 'jpeg')
                return bio.getvalue(), img_data
        return None, None

    def get_render_args(self) -> tuple[list[list[Element]], dict[str, Any]]:
        layout, kwargs = super().get_render_args()
        layout.append([self.options.as_frame('apply_changes')])
        layout.append([HorizontalSeparator()])

        src_img_data, new_img_data = self.cover_images
        if new_img_data is not None:
            layout.append([
                Image(data=src_img_data, size=(250, 250), key='img::cover::src'),
                Text('->', key='txt::cover::arrow'),
                Image(data=new_img_data, size=(250, 250), key='img::cover::new'),
            ])
            layout.append([HorizontalSeparator()])

        dest_album_path = self.album_block.get_dest_path(self.album_info, self.output_base_dir)
        if dest_album_path and self.album.path != dest_album_path:
            layout.append(
                get_a_to_b('Album Rename:', self.album.path.as_posix(), dest_album_path.as_posix(), 'album', 'path')
            )
        else:
            layout.append([Text('Album Path:'), Input(self.album.path.as_posix(), disabled=True, size=(150, 1))])

        common_rows = self.album_block.get_album_diff_rows(self.album_info, self.options['title_case'])
        layout.append([Column(common_rows, key='col::album::diff')])

        layout.append([HorizontalSeparator()])
        layout.append([Text('Track Changes')])

        for path, track_block in self.album_block.track_blocks.items():
            try:
                track_info = self.album_info.tracks[path]
            except KeyError:
                print('Available track paths:')
                for path in self.album_info.tracks:
                    print(f'  - {path!r}')
                raise

            layout.extend(track_block.as_diff_rows(track_info, self.options['title_case']))

        # # TODO: Input sanitization/normalization
        # self.album_info.update_and_move(self.album, None, dry_run=True)
        return layout, kwargs

    @event_handler('opt::title_case', 'opt::add_genre')  # noqa
    def refresh(self, event: str, data: dict[str, Any]):
        self.options.parse(data)
        self.render()

    # @event_handler
    # def apply_changes(self, event: str, data: dict[str, Any]):
    #     pass
