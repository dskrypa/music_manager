"""
View: Diff between original and modified tag values.  Used for both manual and Wiki-based updates.

:author: Doug Skrypa
"""

from functools import cached_property
from io import BytesIO
from typing import Any, Optional

from PySimpleGUI import Text, Input, Image, Column, Element, HSep

from ...files.album import AlbumDir
from ...manager.update import AlbumInfo
from ..constants import LoadingSpinner
from ..options import GuiOptions
from ..progress import Spinner
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

        self.options = GuiOptions(self, disable_on_parsed=False, submit=None)
        self.options.add_bool('dry_run', 'Dry Run', default=True)
        self.options.add_bool('add_genre', 'Add Genre', kwargs={'enable_events': True})
        self.options.add_bool('title_case', 'Title Case', kwargs={'enable_events': True})
        self.options.add_bool('no_album_move', 'Do Not Move Album', kwargs={'enable_events': True})

    @cached_property
    def file_info_map(self):
        return self.album_info.get_file_info_map(self.album)

    @cached_property
    def cover_images(self) -> tuple[Optional[bytes], Optional[bytes], Optional[Image]]:
        if self.album_info.cover_path:
            file_img = self.album_info.get_current_cover(self.file_info_map)
            new_image_obj, new_img_data = self.album_info.get_new_cover(self.album, file_img)
            if new_img_data is not None:
                bio = BytesIO()
                file_img.save(bio, 'jpeg')
                return bio.getvalue(), new_img_data, new_image_obj
        return None, None, None

    def get_dest_album_path(self):
        if self.options['no_album_move']:
            return None

        dest_album_path = self.album_block.get_dest_path(self.album_info, self.output_sorted_dir)
        if dest_album_path and self.album.path != dest_album_path:
            return dest_album_path
        return None

    def get_render_args(self) -> tuple[list[list[Element]], dict[str, Any]]:
        full_layout, kwargs = super().get_render_args()

        layout = [
            [self.options.as_frame('apply_changes')],
            [Text()],
            [HSep(), Text('Common Album Changes'), HSep()],
            [Text()],
        ]

        src_img_data, new_img_data, new_image_obj = self.cover_images
        if new_img_data is not None:
            layout.append([
                # TODO: These need to be made into thumbnails
                Image(data=src_img_data, size=(250, 250), key='img::cover::src'),
                Text('->', key='txt::cover::arrow'),
                Image(data=new_img_data, size=(250, 250), key='img::cover::new'),
            ])
            layout.append([HSep()])

        if dest_album_path := self.get_dest_album_path():
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
            layout.extend(track_block.as_diff_rows(self.album_info.tracks[path], self.options['title_case']))

        workflow = self.as_workflow(
            layout, back_key='edit', back_tooltip='Go back to edit', next_tooltip='Apply changes (save)'
        )
        full_layout.append(workflow)

        return full_layout, kwargs

    @event_handler('opt::title_case', 'opt::add_genre', 'opt::no_album_move')  # noqa
    def refresh(self, event: str, data: dict[str, Any]):
        self.options.parse(data)
        self.render()

    @event_handler('btn::next')  # noqa
    def apply_changes(self, event: str, data: dict[str, Any]):
        self.options.parse(data)
        dry_run = self.options['dry_run']

        with Spinner(LoadingSpinner.blue_dots, message='Applying Changes...') as spinner:
            file_tag_map = {file: info.tags() for file, info in self.file_info_map.items()}
            src_img_data, new_img_data, new_image_obj = self.cover_images
            for file, info in spinner(self.file_info_map.items()):
                file.update_tags(file_tag_map[file], dry_run, add_genre=self.options['add_genre'])
                if new_image_obj is not None:
                    spinner.update()
                    file.set_cover_data(new_image_obj, dry_run, new_img_data)
                spinner.update()
                info.maybe_rename(file, dry_run)

            spinner.update()
            if dest_album_path := self.get_dest_album_path():  # returns None if self.options['no_album_move']
                prefix = '[DRY RUN] Would move' if dry_run else 'Moving'
                self.log.info(f'{prefix} {self.album} -> {dest_album_path.as_posix()}')
                if not dry_run:
                    orig_parent_path = self.album.path.parent
                    self.album.move(dest_album_path)
                    for path in (orig_parent_path, orig_parent_path.parent):
                        self.log.log(19, f'Checking directory: {path}')
                        if path.exists() and next(path.iterdir(), None) is None:
                            self.log.log(19, f'Removing empty directory: {path}')
                            path.rmdir()
