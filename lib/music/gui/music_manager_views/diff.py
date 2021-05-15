"""
View: Diff between original and modified tag values.  Used for both manual and Wiki-based updates.

:author: Doug Skrypa
"""

from functools import cached_property
from typing import TYPE_CHECKING, Optional, Any, Mapping, Union

from PySimpleGUI import Text, Image, Column, HSep, Button

from ...files.album import AlbumDir
from ...manager.update import AlbumInfo, TrackInfo
from ..base_view import event_handler, Event, EventData, RenderArgs
from ..constants import LoadingSpinner
from ..elements.inputs import ExtInput
from ..options import GuiOptions
from ..progress import Spinner
from .formatting import AlbumFormatter
from .main import MainView
from .utils import get_a_to_b

if TYPE_CHECKING:
    from PIL.Image import Image as PILImage
    from ...files.track.track import SongFile

__all__ = ['AlbumDiffView']


class AlbumDiffView(MainView, view_name='album_diff'):
    def __init__(
        self,
        album: AlbumDir,
        album_info: AlbumInfo,
        album_formatter: AlbumFormatter = None,
        options: Union[GuiOptions, Mapping[str, Any]] = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.album = album
        self.album_info = album_info
        self.album_formatter = album_formatter or AlbumFormatter(self, self.album)
        self.album_formatter.view = self
        self.album_formatter.album_info = album_info

        self.options = GuiOptions(self, disable_on_parsed=False, submit=None)
        self.options.add_bool('dry_run', 'Dry Run', default=False)
        self.options.add_bool('add_genre', 'Add Genre', default=True, enable_events=True, tooltip='Add any specified genres instead of replacing them')
        self.options.add_bool('title_case', 'Title Case', enable_events=True)
        self.options.add_bool('no_album_move', 'Do Not Move Album', enable_events=True)
        self.options.add_bool('rename_in_place', 'Rename Album In-Place', enable_events=True)
        self.options.update(options)

    @cached_property
    def file_info_map(self):
        return self.album_info.get_file_info_map(self.album)

    @property
    def cover_images(self) -> Optional[tuple[Image, Image, 'PILImage', bytes]]:
        return self.album_formatter.get_cover_image_diff(self.album_info)

    def get_dest_album_path(self):
        if self.options['no_album_move']:
            return None

        dest_base_dir = self.album.path.parents[2] if self.options['rename_in_place'] else self.output_sorted_dir
        dest_album_path = self.album_formatter.get_dest_path(self.album_info, dest_base_dir)
        if dest_album_path and self.album.path != dest_album_path:
            return dest_album_path
        return None

    def get_render_args(self) -> RenderArgs:
        full_layout, kwargs = super().get_render_args()
        ele_binds = {}
        options_frame = self.options.as_frame('apply_changes')
        if self.last_view and self.last_view.name != 'album':
            top_side_kwargs = dict(size=(6, 1), pad=(0, 0), font=('Helvetica', 20))
            edit_button = Button('\u2190 Edit', key='edit', visible=True, **top_side_kwargs)
            edit_col = Column([[edit_button]], key='col::edit', expand_x=True)
            right_spacer = Text(key='spacer::1', **top_side_kwargs)
            first_row = [edit_col, options_frame, right_spacer]
            self.binds['<Control-e>'] = 'edit'
        else:
            first_row = [options_frame]

        layout = [first_row, [Text()], [HSep(), Text('Common Album Changes'), HSep()], [Text()]]

        if diff_imgs := self.cover_images:
            src_img_ele, new_img_ele = diff_imgs[:2]
            img_row = [src_img_ele, Text('\u2794', key='txt::cover::arrow', font=('Helvetica', 20)), new_img_ele]
            img_diff_col = Column([img_row], key='col::img_diff', justification='center')
            layout.extend([[img_diff_col], [HSep()]])

        if dest_album_path := self.get_dest_album_path():
            layout.append(get_a_to_b('Album Rename:', self.album.path, dest_album_path, 'album', 'path'))
        else:
            layout.append([Text('Album Path:'), ExtInput(self.album.path.as_posix(), disabled=True, size=(150, 1))])

        title_case, add_genre = self.options['title_case'], self.options['add_genre']
        if common_rows := self.album_formatter.get_album_diff_rows(self.album_info, title_case, add_genre):
            layout.append([Column(common_rows, key='col::album::diff')])
            layout.append([Text()])
        else:
            layout.extend([[Text()], [Text('No common album tag changes.', justification='center')], [Text()]])

        layout.append([HSep(), Text('Track Changes'), HSep()])
        for path, track_formatter in self.album_formatter.track_formatters.items():
            layout.append([Text()])
            layout.extend(track_formatter.as_diff_rows(self.album_info.tracks[path], title_case, add_genre))

        workflow = self.as_workflow(layout, next_tooltip='Apply changes (save)', scrollable=True)
        full_layout.append(workflow)

        return full_layout, kwargs, ele_binds

    def _back_kwargs(self, last: 'MainView') -> dict[str, Any]:
        if last.name == 'album':
            return {'editing': True}
        return {}

    @event_handler('btn::back')
    def back(self, event: Event, data: EventData):
        from .album import AlbumView

        return super().back(event, data, AlbumView)

    @event_handler('opt::*')
    def refresh(self, event: Event, data: EventData):
        self.options.parse(data)
        self.render()
        if self.options['no_album_move']:
            self.window['opt::rename_in_place'].update(disabled=True)
            self.window['opt::no_album_move'].update(disabled=False)
        elif self.options['rename_in_place']:
            self.window['opt::no_album_move'].update(disabled=True)
            self.window['opt::rename_in_place'].update(disabled=False)
        else:
            self.window['opt::rename_in_place'].update(disabled=False)
            self.window['opt::no_album_move'].update(disabled=False)

    @event_handler('btn::next')
    def apply_changes(self, event: Event, data: EventData):
        from .album import AlbumView

        self.options.parse(data)
        dry_run = self.options['dry_run']

        with Spinner(LoadingSpinner.blue_dots, message='Applying Changes...') as spinner:
            file_tag_map = {file: info.tags() for file, info in self.file_info_map.items()}
            new_image_obj, new_img_data = self.cover_images[-2:] if self.cover_images else (None, None)
            for file, info in spinner(self.file_info_map.items()):  # type: SongFile, TrackInfo
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

        if not dry_run:
            return AlbumView(self.album, last_view=self)
