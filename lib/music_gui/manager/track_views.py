"""

"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from tk_gui.views.view import View

from music_gui.elements.track_info import TrackInfoFrame, SongFileFrame
from music_gui.utils import AlbumIdentifier, get_album_dir, get_album_info, with_separators

if TYPE_CHECKING:
    from tk_gui.typing import Layout
    from music.files.album import AlbumDir
    from music.manager.update import AlbumInfo

__all__ = ['TrackInfoView', 'SongFileView']
log = logging.getLogger(__name__)


class TrackInfoView(View, title='Track Info'):
    window_kwargs = {'exit_on_esc': True}

    def __init__(self, album: AlbumIdentifier, **kwargs):
        super().__init__(**kwargs)
        self.album: AlbumInfo = get_album_info(album)

    def get_init_layout(self) -> Layout:
        return with_separators(map(TrackInfoFrame, self.album.tracks.values()), True)


class SongFileView(View, title='Track Info'):
    window_kwargs = {'exit_on_esc': True}

    def __init__(self, album: AlbumIdentifier, **kwargs):
        super().__init__(**kwargs)
        self.album: AlbumDir = get_album_dir(album)

    def get_init_layout(self) -> Layout:
        return with_separators(map(SongFileFrame, self.album), True)
