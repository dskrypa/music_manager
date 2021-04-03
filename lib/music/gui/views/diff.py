"""
View: Diff between original and modified tag values.  Used for both manual and Wiki-based updates.

:author: Doug Skrypa
"""

from functools import cached_property
from io import BytesIO
from typing import Any, Optional

from PySimpleGUI import Text, Input, Image, Column, Element, HSep

from ...files.album import AlbumDir
from ...files.track.track import SongFile
from ...manager.update import AlbumInfo, TrackInfo
from ..options import GuiOptions, GuiOptionError
from .base import event_handler
from .formatting import AlbumBlock
from .main import MainView
from .utils import get_a_to_b

__all__ = ['AlbumDiffView']


class AlbumDiffView(MainView, view_name='album_diff'):
    def __init__(self, album: AlbumDir, album_info: AlbumInfo, album_block: AlbumBlock = None):
        super().__init__()
        self.album = album
        self.album_info = album_info
        self.album_block = album_block or AlbumBlock(self, self.album)
        self.album_block.view = self

        # self.options = GuiOptions(self, disable_on_parsed=False, submit='Save')
        self.options = GuiOptions(self, disable_on_parsed=False, submit=None)
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
        full_layout, kwargs = super().get_render_args()

        layout = []  # noqa
        layout.append([self.options.as_frame('apply_changes')])
        layout.extend([[Text()], [HSep(), Text('Common Album Changes'), HSep()], [Text()]])

        src_img_data, new_img_data = self.cover_images
        if new_img_data is not None:
            layout.append([
                Image(data=src_img_data, size=(250, 250), key='img::cover::src'),
                Text('->', key='txt::cover::arrow'),
                Image(data=new_img_data, size=(250, 250), key='img::cover::new'),
            ])
            layout.append([HSep()])

        dest_album_path = self.album_block.get_dest_path(self.album_info, self.output_sorted_dir)
        if dest_album_path and self.album.path != dest_album_path:
            layout.append(get_a_to_b('Album Rename:', self.album.path, dest_album_path, 'album', 'path'))
        else:
            layout.append([Text('Album Path:'), Input(self.album.path.as_posix(), disabled=True, size=(150, 1))])

        if common_rows := self.album_block.get_album_diff_rows(self.album_info, self.options['title_case']):
            layout.append([Column(common_rows, key='col::album::diff')])
            layout.append([Text()])
        else:
            layout.extend([[Text()], [Text('No common album tag changes.', justification='center')], [Text()]])

        layout.append([HSep(), Text('Track Changes'), HSep()])
        for path, track_block in self.album_block.track_blocks.items():
            layout.append([Text()])
            try:
                track_info = self.album_info.tracks[path]
            except KeyError:
                print('Available track paths:')
                for path in self.album_info.tracks:
                    print(f'  - {path!r}')
                raise

            layout.extend(track_block.as_diff_rows(track_info, self.options['title_case']))

        workflow = self.as_workflow(
            layout, back_key='edit', back_tooltip='Go back to edit', next_tooltip='Apply changes (save)'
        )
        full_layout.append(workflow)

        # self.album_info.update_and_move(self.album, None, dry_run=True)
        return full_layout, kwargs

    @event_handler('opt::title_case', 'opt::add_genre')  # noqa
    def refresh(self, event: str, data: dict[str, Any]):
        self.options.parse(data)
        self.render()

    @event_handler('btn::next')  # noqa
    def apply_changes(self, event: str, data: dict[str, Any]):
        self.options.parse(data)
