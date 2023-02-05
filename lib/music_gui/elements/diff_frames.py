"""

"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from ds_tools.caching.decorators import cached_property

from tk_gui.elements import ListBox, CheckBox, HorizontalSeparator, Spacer
from tk_gui.elements.buttons import Button
from tk_gui.elements.frame import InteractiveFrame, Frame
from tk_gui.elements.rating import Rating
from tk_gui.elements.text import Text
from tk_gui.options import GuiOptions

from music.files import AlbumDir, SongFile
from music.manager.update import TrackInfo, AlbumInfo
from ..utils import get_album_dir, get_track_file
from ..utils import zip_maps
from .images import AlbumCoverImageBuilder

if TYPE_CHECKING:
    from tk_gui.typing import Layout, XY, PathLike
    from music.typing import StrOrStrs

__all__ = ['AlbumDiffFrame']
log = logging.getLogger(__name__)

LRG_FONT = ('Helvetica', 20)


class AlbumDiffFrame(InteractiveFrame):
    old_info: AlbumInfo
    new_info: AlbumInfo
    album_dir: AlbumDir
    options: GuiOptions
    output_sorted_dir: Path

    def __init__(
        self,
        old_info: AlbumInfo,
        new_info: AlbumInfo,
        options: GuiOptions,
        output_sorted_dir: Path,
        show_edit: bool = False,
        album_dir: AlbumDir = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.old_info = old_info
        self.new_info = new_info
        self.album_dir = album_dir or get_album_dir(old_info)
        self.options = options
        self.output_sorted_dir = output_sorted_dir
        self._found_common_tag_change = False
        self._show_edit = show_edit

    @cached_property
    def new_album_path(self) -> Path | None:
        if self.options['no_album_move']:
            return None
        return self.new_info.get_new_path(None if self.options['rename_in_place'] else self.output_sorted_dir)

    # region Layout

    def get_custom_layout(self) -> Layout:
        yield from self.build_header()
        yield from self.build_cover_diff()
        yield from self.build_path_diff()
        yield from self.build_common_tag_diff()
        yield from self.build_track_diff()
        # Force content to be top-aligned (there doesn't seem to be a better way).  Side/anchor/etc for this frame
        # were ineffective.
        yield [Spacer((10, 500), side='t')]

    def build_header(self) -> Layout:
        options_frame = self.options.as_frame('apply_changes', change_cb=self.update_options, side='t')
        if not self._show_edit:
            yield [options_frame]
        else:
            top_side_kwargs = dict(size=(6, 1), pad=(0, 0), font=LRG_FONT)
            edit_button_col = Frame([[Button('\u2190 Edit', key='edit', **top_side_kwargs)]], expand=True, fill='x')
            yield [edit_button_col, options_frame, Text(**top_side_kwargs)]

        yield [Text()]
        yield [HorizontalSeparator(), Text('Common Album Changes'), HorizontalSeparator()]
        yield [Text()]

    def build_cover_diff(self) -> Layout:
        if not (new_cover_path := self.new_info.cover_path):
            return

        old_cover_img, new_cover_img = AlbumCoverImageBuilder(self.old_info).make_diff_thumbnails(new_cover_path)
        yield [old_cover_img, Text('\u2794', font=LRG_FONT), new_cover_img]
        yield [HorizontalSeparator()]

    def build_path_diff(self) -> Layout:
        if new_album_path := self.new_album_path:
            yield from get_a_to_b('Album Rename:', self.album_dir.path, new_album_path)
        else:
            yield [Text('Album Path:'), Text(self.album_dir.path.as_posix(), use_input_style=True, size=(150, 1))]

    def build_common_tag_diff(self) -> Layout:
        yield from self._build_common_tag_diff()
        if not self._found_common_tag_change:
            yield [Text()]
            yield [Text('No common album tag changes.', justify='center')]

        yield [Text()]

    def _build_common_tag_diff(self) -> Layout:
        title_case, add_genre = self.options['title_case'], self.options['add_genre']
        old_data = self.old_info.to_dict(title_case, skip={'tracks'})
        new_data = self.new_info.to_dict(title_case, skip={'tracks'})
        for key, old_val, new_val in zip_maps(old_data, new_data):
            self._found_common_tag_change = True
            if key == 'genre' and add_genre:
                new_val = sorted(_str_set(new_val) | _str_set(old_val))
            if (old_val or new_val) and old_val != new_val:
                yield _diff_row(key, old_val, new_val)

    def build_track_diff(self) -> Layout:
        yield [HorizontalSeparator(), Text('Track Changes'), HorizontalSeparator()]
        title_case = self.options['title_case']
        old_genres = self.old_info.get_genre_set(title_case)
        new_genres = self.new_info.get_genre_set(title_case)
        if self.options['add_genre']:
            new_genres.update(old_genres)

        genres = (old_genres, new_genres)
        new_tracks = self.new_info.tracks
        for path_str, old_track_info in self.old_info.tracks.items():
            yield [TrackDiffFrame(old_track_info, new_tracks[path_str], self.options, genres)]

    # endregion

    def update_options(self, *args):
        self.options.parse(self.window.results)
        if self.options['no_album_move']:
            self.window['opt::rename_in_place'].disable()  # noqa
            self.window['opt::no_album_move'].enable()  # noqa
        elif self.options['rename_in_place']:
            self.window['opt::no_album_move'].disable()  # noqa
            self.window['opt::rename_in_place'].enable()  # noqa
        else:
            self.window['opt::rename_in_place'].enable()  # noqa
            self.window['opt::no_album_move'].enable()  # noqa


class TrackDiffFrame(InteractiveFrame):
    old_info: TrackInfo
    new_info: TrackInfo
    song_file: SongFile
    options: GuiOptions
    genres: tuple[set[str], set[str]]

    def __init__(
        self,
        old_info: TrackInfo,
        new_info: TrackInfo,
        options: GuiOptions,
        genres: tuple[set[str], set[str]],
        song_file: SongFile = None,
        **kwargs,
    ):
        kwargs.setdefault('size', (850, None))
        kwargs.setdefault('side', 't')
        kwargs.setdefault('pack_propagate', False)
        super().__init__(**kwargs)
        self.old_info = old_info
        self.new_info = new_info
        self.song_file = song_file or get_track_file(old_info)
        self.options = options
        self.genres = genres

    def get_custom_layout(self) -> Layout:
        yield [Text()]
        yield [HorizontalSeparator()]
        yield from self.build_name_diff()
        yield from self.build_tag_diff()

    def build_name_diff(self) -> Layout:
        old_name = self.song_file.path.name
        new_name = self.new_info.expected_name(self.song_file)
        if old_name != new_name:
            yield from get_a_to_b('File Rename:', old_name, new_name)
        else:
            yield [Text('File:'), Text(old_name, use_input_style=True, size=(50, 1)), Text('(no change)')]

    def build_tag_diff(self) -> Layout:
        title_case = self.options['title_case']
        old_data = self.old_info.to_dict(title_case)
        new_data = self.new_info.to_dict(title_case)
        for key, old_val, new_val in zip_maps(old_data, new_data):
            if key == 'genre':
                yield from self.build_genre_diff(old_val, new_val)
            else:
                if not ((old_val or new_val) and old_val != new_val):
                    continue

                if key == 'rating':
                    old_ele = Rating(old_val, show_value=True, pad=(0, 0), disabled=True)
                    new_ele = Rating(new_val, show_value=True, pad=(0, 0), disabled=True)
                    yield [label_ele(key), Text('from'), old_ele, Text('to'), new_ele]
                else:
                    yield _diff_row(key, old_val, new_val)

    def build_genre_diff(self, old_val: StrOrStrs, new_val: StrOrStrs) -> Layout:
        old_alb_vals, new_alb_vals = self.genres
        new_vals = (_str_set(new_val) | new_alb_vals) if new_val else new_alb_vals.copy()
        old_vals = _str_set(old_val)
        if self.options['add_genre']:
            new_vals.update(old_vals)
        if (old_vals != old_alb_vals or new_vals != new_alb_vals) and ((old_vals or new_vals) and old_vals != new_vals):
            yield _diff_row('genre', sorted(old_vals), sorted(new_vals))


# endregion


def _diff_row(key: str, old_val, new_val):
    # log.debug(f'album: {key} is different: {old_val=!r} != {new_val=!r}')
    old_ele = _build_diff_value_ele(key, old_val)
    new_ele = _build_diff_value_ele(key, new_val)
    return [label_ele(key), Text('from'), old_ele, Text('to'), new_ele]


def _build_diff_value_ele(key: str, value) -> CheckBox | ListBox | Text:
    match value:
        case bool():
            return CheckBox('', default=value, pad=(0, 0), disabled=True)
        case list():
            kwargs = {'size': (45, len(value)), 'pad': (5, 0), 'border': 2}
            return ListBox(value, default=value, disabled=True, scroll_y=False, **kwargs)
        case _:
            kwargs = {'use_input_style': True}
            if key.startswith('wiki_'):
                kwargs['link'] = True
            return Text('' if value is None else value, size=(45, 1), **kwargs)


def get_a_to_b(label: str, old_val: PathLike, new_val: PathLike) -> Layout:
    old_ele, old_len = _diff_ele(old_val)
    new_ele, new_len = _diff_ele(new_val)
    if old_len + new_len > 200:
        yield [Text(label), old_ele]
        # yield [Image(size=(len(label) * 7, 1)), Text('\u2794', font=('Helvetica', 15), size=(2, 1)), new_ele]
        yield [Spacer(size=(len(label) * 7, 1)), Text('\u2794', font=('Helvetica', 15), size=(2, 1)), new_ele]
    else:
        yield [Text(label), old_ele, Text('\u2794', font=('Helvetica', 15), size=(2, 1)), new_ele]


def _diff_ele(value: PathLike) -> tuple[Text, int]:
    if isinstance(value, Path):
        value = value.as_posix()
    kwargs = {'use_input_style': True}
    if (val_len := len(value)) > 50:
        kwargs['size'] = (val_len, 1)
    else:
        kwargs['size'] = (50, 1)
    return Text(value, **kwargs), val_len


def _str_set(values: StrOrStrs) -> set[str]:
    if isinstance(values, str):
        return {values}
    return set(values)


def label_ele(text: str, size: XY = (15, 1), **kwargs) -> Text:
    return Text(text.replace('_', ' ').title(), size=size, **kwargs)
