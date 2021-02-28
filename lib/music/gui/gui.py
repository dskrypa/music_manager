"""
Music manager GUI using PySimpleGUI.  WIP.

:author: Doug Skrypa
"""

import logging
from io import BytesIO
from pathlib import Path
from typing import Dict, Tuple, Any, Optional, Union, List

from PySimpleGUI import Text, Button, Column, HorizontalSeparator, Input, Image, Multiline, Element
from PySimpleGUI import popup_animated, theme

from ..constants import typed_tag_name_map
from ..files.album import AlbumDir
from ..files.track.track import SongFile
from .base import GuiBase, event_handler
from .constants import LoadingSpinner
from .prompts import directory_prompt

__all__ = ['MusicManagerGui']
log = logging.getLogger(__name__)


class MusicManagerGui(GuiBase):
    def __init__(self):
        theme('SystemDefaultForReal')
        super().__init__(title='Music Manager', resizable=True)
        initial_layout = [
            Text('Music Manager'),
            Button('Select Album', enable_events=True, key='select_album'),
        ]
        self.set_layout([initial_layout])
        self._album = None
        self._view = None

    def _select_album_path(self) -> Optional[Path]:
        if path := directory_prompt('Select Album'):
            log.debug(f'Selected album {path=}')
            self._album = AlbumDir(path)
        else:
            self._album = None
        return path

    @property
    def album(self) -> Optional[AlbumDir]:
        if self._album is None:
            self._select_album_path()
        return self._album

    @album.setter
    def album(self, path: Union[str, Path]):
        self._album = AlbumDir(path)

    @event_handler('select_album')
    def select_album(self, event: str, data: Dict[str, Any]):
        self.show_tracks()

    def show_tracks(self):
        self.window.hide()
        if not (album := self.album):
            self.window.un_hide()
            self.set_layout([[Text('No album selected.')]])
            return

        track_rows = []
        for i, track in enumerate(album):
            popup_animated(LoadingSpinner.blue_dots, 'Loading...')
            track_rows.append([HorizontalSeparator()])
            track_rows.append(
                [Text(f'{track.path.as_posix()} [{track.length_str}] ({track.tag_version})')]
            )
            track_rows.append(
                [Column([[get_cover_image(track)]]), Column(get_track_data(track))]
            )

        rows = [[Text(f'Album: {album.path}')], [Column(track_rows, scrollable=True, size=(800, 500))]]
        self.set_layout(rows)
        self._view = 'tracks'
        popup_animated(None)  # noqa

    @event_handler('window_resized')
    def window_resized(self, event: str, data: Dict[str, Any]):
        log.debug(f'Window size changed from {data["old_size"]} to {data["new_size"]}')
        if self._view == 'tracks':
            log.debug(f'Expanding columns on {self.window}')
            expand_columns(self.window.Rows)


def expand_columns(rows: List[List[Element]]):
    for row in rows:
        for ele in row:
            if isinstance(ele, Column):
                ele.expand(True, True)
            try:
                ele_rows = ele.Rows
            except AttributeError:
                pass
            else:
                log.debug(f'Expanding columns on {ele}')
                expand_columns(ele_rows)


def get_track_data(track: SongFile):
    tag_name_map = typed_tag_name_map.get(track.tag_type, {})
    rows = []
    longest = 0
    for tag, val in sorted(track.tags.items()):
        tag_name = tag_name_map.get(tag[:4], tag)
        if tag_name == 'Album Cover':
            continue

        longest = max(longest, len(tag_name))
        if tag_name == 'Lyrics':
            rows.append([Text(tag_name), Multiline(val, size=(45, 4))])
        else:
            rows.append([Text(tag_name), Input(val)])

    for row in rows:
        row[0].Size = (longest, 1)

    return rows


def get_cover_image(track: SongFile, size: Tuple[int, int] = (250, 250)) -> Image:
    try:
        image = track.get_cover_image()
    except Exception as e:
        log.error(f'Unable to load cover image for {track}')
        return Image(size=size)
    else:
        image.thumbnail((250, 250))
        bio = BytesIO()
        image.save(bio, format='PNG')
        return Image(data=bio.getvalue(), size=size)
