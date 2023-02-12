"""

"""

from __future__ import annotations

import logging
from abc import ABC
from typing import TYPE_CHECKING

from ds_tools.caching.decorators import cached_property
from tk_gui.elements import HorizontalSeparator, Button, Text
from tk_gui.popups import BoolPopup
from tk_gui.options import OldGuiOptions

from music.files.track.track import SongFile
from music.files.album import AlbumDir
from music_gui.elements.file_frames import SongFileFrame, SelectableSongFileFrame
from music_gui.elements.helpers import IText
from music_gui.elements.info_frames import TrackInfoFrame
from music_gui.utils import LogAndPopupHelper, AlbumIdentifier, get_album_dir, get_album_info, with_separators
from .base import BaseView

if TYPE_CHECKING:
    from tkinter import Event
    from tk_gui.typing import Layout
    from music.manager.update import AlbumInfo

__all__ = ['TrackInfoView', 'SongFileView']
log = logging.getLogger(__name__)


class BaseTrackView(BaseView, ABC, title='Music Manager - Track Info', scroll_y=True):
    window_kwargs = BaseView.window_kwargs | {'exit_on_esc': True}


class TrackInfoView(BaseTrackView):
    def __init__(self, album: AlbumIdentifier, **kwargs):
        super().__init__(**kwargs)
        self.album: AlbumInfo = get_album_info(album)

    def get_inner_layout(self) -> Layout:
        yield from with_separators(map(TrackInfoFrame, self.album.tracks.values()), True)


class SongFileView(BaseTrackView):
    def __init__(self, album: AlbumIdentifier, **kwargs):
        super().__init__(**kwargs)
        self.album: AlbumDir = get_album_dir(album)

    def get_inner_layout(self) -> Layout:
        yield from with_separators(map(SongFileFrame, self.album), True)


class SelectableSongFileView(SongFileView):
    def __init__(self, album: AlbumIdentifier, **kwargs):
        super().__init__(album, **kwargs)
        self._track_frames: list[SelectableSongFileFrame] = []

    # region Layout / Elements

    @cached_property
    def options(self) -> OldGuiOptions:
        options = OldGuiOptions(None)
        options.add_bool('dry_run', 'Dry Run', default=False)
        return options

    def get_pre_window_layout(self) -> Layout:
        yield from super().get_pre_window_layout()
        del_button = Button('Delete\nSelected Tags', focus=False, side='bottom', cb=self.delete_selected_tags)
        yield [self.options.as_frame(), Text('Album:', anchor='s'), IText(self.album.path, anchor='s'), del_button]
        yield [HorizontalSeparator()]

    def get_inner_layout(self) -> Layout:
        for i, track in enumerate(self.album):
            frame = SelectableSongFileFrame(track, multi_select_cb=self.multi_select_cb)
            self._track_frames.append(frame)
            if i:
                yield [HorizontalSeparator()]
            yield [frame]

    # endregion

    # region Event Handling

    def multi_select_cb(self, event: Event):
        try:
            element = self.window[event.widget]
            track_frame: SelectableSongFileFrame = element.data['track_frame']  # noqa
            tag_id = element.data['tag_id']  # noqa
            target_value = next(not row[1].value for row in track_frame.get_tag_rows(tag_id) if element in row)
        except (AttributeError, KeyError, TypeError, StopIteration):
            return
        # log.debug(f'Setting all {tag_id=} values to {target_value=}')
        for row_box in (row[1] for frame in self._track_frames for row in frame.get_tag_rows(tag_id)):
            if row_box is not element:
                # If the element that was clicked was the checkbox itself, then it needs to be skipped here.
                # The bind callback happens before the normal checkbox's toggle action, which uses the value at the
                # time it is executed.  If the target value was set for it here, it would be reset by that action.
                row_box.value = target_value  # noqa

    def delete_selected_tags(self, event: Event):
        dry_run = self.options.parse(self.window.results)['dry_run']
        with LogAndPopupHelper('Results', dry_run, 'No tags were selected for deletion') as lph:
            for track, tag_ids in self.get_tags_to_delete().items():
                lph.write('delete', f'{len(tag_ids)} tags from {track.path.name}: ' + ', '.join(sorted(tag_ids)))
                if not lph.dry_run:
                    track.remove_tags(tag_ids)

        if lph.took_action():
            return self.set_next_view(self.album)
        else:
            for track_frame in self._track_frames:
                track_frame.refresh()

    def get_tags_to_delete(self):
        to_delete = {}
        for track_frame in self._track_frames:
            if not (to_del_tag_ids := track_frame.to_delete):
                continue

            to_delete[track_frame.track] = track_to_del = set()
            for tag_id in to_del_tag_ids:
                rows = track_frame.get_tag_rows(tag_id)
                if len(rows) > 1 and not delete_all_tag_vals_prompt(track_frame.track, tag_id):
                    return None

                track_to_del.add(tag_id)

        return to_delete

    # endregion


def delete_all_tag_vals_prompt(track: SongFile, tag_id: str) -> bool:
    message = (
        f'Found multiple tags for file={track.path.as_posix()!r} with {tag_id=}.'
        ' Continue to delete all values for this tag?'
    )
    popup = BoolPopup(message, 'Yes, delete all', 'Cancel', 'FT', title='Delete All Tag Values?', bind_esc=True)
    return popup.run()
