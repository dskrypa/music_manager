"""
Gui Views

:author: Doug Skrypa
"""

import logging
from dataclasses import fields
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, Union

from PySimpleGUI import Text, Button, Column, Element, Checkbox, Frame, Submit, Input

from ...files.album import AlbumDir
from ...files.changes import get_common_changes
from ...files.track.track import SongFile
from ...manager.update import AlbumInfo, TrackInfo, TRACK_NAME_FORMAT
from .base import ViewManager, event_handler
from .main import MainView

__all__ = ['AlbumDiffView']
log = logging.getLogger(__name__)


class AlbumDiffView(MainView, view_name='album_diff'):
    def __init__(self, mgr: 'ViewManager', album: AlbumDir, album_info: AlbumInfo):
        super().__init__(mgr)
        self.album = album
        self.album_info = album_info
        self.dry_run = False
        self.add_genre = True

    def get_render_args(self) -> tuple[list[list[Element]], dict[str, Any]]:
        layout, kwargs = super().get_render_args()

        album_dir = self.album_info.album_dir
        file_info_map = self.album_info.get_file_info_map(album_dir)
        file_tag_map = {file: info.tags() for file, info in file_info_map.items()}
        image, img_data = self.album_info.get_new_cover(album_dir, file_info_map)
        common_changes = get_common_changes(
            album_dir, file_tag_map, dry_run=self.dry_run, add_genre=self.add_genre, show=False
        )

        """
        _fmt = '  - {{:<{}s}}{}{{:>{}s}}{}{{}}'

        if changes:
            uprint(colored('{} {} by changing...'.format('[DRY RUN] Would update' if dry_run else 'Updating', obj), color))
            for tag_name, (orig_val, new_val) in changes.items():
                if tag_name == 'title':
                    bg, reset, w = 20, False, 20
                else:
                    bg, reset, w = None, True, 14
    
                orig_repr = repr(orig_val)
                fmt = _fmt.format(
                    name_width + w,
                    colored(' from ', 15, bg, reset=reset),
                    orig_width - (mono_width(orig_repr) - len(orig_repr)) + w,
                    colored(' to ', 15, bg, reset=reset),
                )
    
                uprint(colored(
                    fmt.format(
                        colored(tag_name, 14, bg, reset=reset),
                        colored(orig_repr, 11, bg, reset=reset),
                        colored(repr(new_val), 10, bg, reset=reset),
                    ),
                    bg_color=bg,
                ))
        else:
            prefix = '[DRY RUN] ' if dry_run else ''
            uprint(colored(f'{prefix}No changes necessary for {obj}', color))
        """

        # for file, info in file_info_map.items():
        #     log.debug(f'Matched {file} to {info.title}')
        #     file.update_tags(file_tag_map[file], dry_run, no_log=common_changes, add_genre=add_genre)
        #     if image is not None:
        #         file.set_cover_data(image, dry_run, img_data)
        #     maybe_rename_track(file, info.name or info.title, info.num, dry_run)

        # # TODO: Make dry_run not default
        # # TODO: Implement gui-based diff
        # # TODO: Input sanitization/normalization
        self.album_info.update_and_move(self.album, None, dry_run=True)

        return layout, kwargs


def maybe_rename_track(file: SongFile, track_name: str, num: int, dry_run: bool = False):
    prefix = '[DRY RUN] Would rename' if dry_run else 'Renaming'
    filename = TRACK_NAME_FORMAT(track=track_name, ext=file.ext, num=num)
    if file.path.name != filename:
        rel_path = Path(file.rel_path)
        log.info(f'{prefix} {rel_path.parent}/{rel_path.name} -> {filename}')
        if not dry_run:
            file.rename(file.path.with_name(filename))
