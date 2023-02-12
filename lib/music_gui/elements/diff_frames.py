"""

"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Mapping

from ds_tools.caching.decorators import cached_property

from tk_gui.elements import Element, ListBox, CheckBox, HorizontalSeparator, Spacer, Text, Button
from tk_gui.elements.frame import InteractiveFrame, Frame, BasicRowFrame
from tk_gui.elements.rating import Rating

from music.files import AlbumDir, SongFile
from music.manager.update import TrackInfo, AlbumInfo
from ..utils import get_album_dir, get_track_file
from ..utils import zip_maps
from .helpers import IText, section_header
from .images import AlbumCoverImageBuilder

if TYPE_CHECKING:
    from tk_gui.options import GuiOptions
    from tk_gui.typing import Layout, XY, PathLike, TraceCallback
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
        *,
        output_sorted_dir: Path,
        update_options_cb: TraceCallback,
        options: GuiOptions,
        show_edit: bool = False,
        album_dir: AlbumDir = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.old_info = old_info
        self.new_info = new_info
        self.album_dir = album_dir or get_album_dir(old_info)
        self.options = options
        self._update_options_cb = update_options_cb
        self.output_sorted_dir = output_sorted_dir
        self._found_common_tag_change = False
        self._show_edit = show_edit

    @property
    def new_album_path(self) -> Path | None:
        if self.options['no_album_move']:
            return None
        # TODO: Rename in place dir may be wrong
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
        if not self._show_edit:
            yield [self.options_frame]
        else:
            top_side_kwargs = dict(size=(6, 1), pad=(0, 0), font=LRG_FONT)
            edit_button_col = Frame([[Button('\u2190 Edit', key='edit', **top_side_kwargs)]], expand=True, fill='x')
            yield [edit_button_col, self.options_frame, Text(**top_side_kwargs)]

        yield [Text()]
        yield section_header('Common Album Changes')
        yield [Text()]

    def build_cover_diff(self) -> Layout:
        if not (new_cover_path := self.new_info.cover_path):
            return

        old_cover_img, new_cover_img = AlbumCoverImageBuilder(self.old_info).make_diff_thumbnails(new_cover_path)
        yield [BasicRowFrame([old_cover_img, Text('\u2794', font=LRG_FONT), new_cover_img], anchor='c', side='t')]
        yield [HorizontalSeparator()]

    def build_path_diff(self) -> Layout:
        yield [*self.path_diff_eles]

    @cached_property
    def path_diff_eles(self) -> tuple[Frame, BasicRowFrame]:
        # Used by AlbumDiffView to toggle visibility when options change.
        show_rename = not self.options['no_album_move']
        old_path = self.album_dir.path
        paths = (old_path, self.new_info.get_new_path(None), self.new_info.get_new_path(self.output_sorted_dir))
        split = max(len(p.as_posix()) for p in paths) >= 50

        rename_ele = Frame(
            get_a_to_b('Album Rename:', old_path, self.new_album_path, split), visible=show_rename, pad=(0, 0)
        )
        no_change_row = [label_ele('Album Path:'), IText(old_path, size=(150, 1)), Text('(no change)')]
        no_change_ele = BasicRowFrame(no_change_row, visible=not show_rename, pad=(0, 0))
        return rename_ele, no_change_ele

    def build_common_tag_diff(self) -> Layout:
        yield from self._build_common_tag_diff()
        if not self._found_common_tag_change:
            yield [Text()]
            yield [Text('No common album tag changes.', justify='center')]

        yield [Text()]

    def _build_common_tag_diff(self) -> Layout:
        title_case, repl_genres = self.options['title_case'], self.options['repl_genres']
        old_data = self.old_info.to_dict(title_case, skip={'tracks'})
        new_data = self.new_info.to_dict(title_case, skip={'tracks'})
        for key, old_val, new_val in zip_maps(old_data, new_data):
            self._found_common_tag_change = True
            if key == 'genre' and not repl_genres:
                new_val = sorted(_str_set(new_val) | _str_set(old_val))
            if (old_val or new_val) and old_val != new_val:
                yield _diff_row(key, old_val, new_val)

    def build_track_diff(self) -> Layout:
        yield section_header('Track Changes')
        title_case = self.options['title_case']
        old_genres = self.old_info.get_genre_set(title_case)
        new_genres = self.new_info.all_common_genres(title_case)
        if not self.options['repl_genres']:
            new_genres.update(old_genres)

        genres = (old_genres, new_genres)
        new_tracks = self.new_info.tracks
        for path_str, old_track_info in self.old_info.tracks.items():
            yield [TrackDiffFrame(old_track_info, new_tracks[path_str], self.options, genres)]

    # endregion

    # region Options

    @cached_property
    def options_frame(self) -> Frame:
        frame = self.options.as_frame(change_cb=self._update_options_cb, side='t')
        key_ele_map = {key: ele for row in frame.rows for ele in row.elements if (key := getattr(ele, 'key', None))}
        self.update_option_states(key_ele_map)
        return frame

    def update_option_states(self, key_ele_map: Mapping[str, CheckBox | Element]):
        if self.options['no_album_move']:
            key_ele_map['opt::rename_in_place'].disable()
            key_ele_map['opt::no_album_move'].enable()
        elif self.options['rename_in_place']:
            key_ele_map['opt::no_album_move'].disable()
            key_ele_map['opt::rename_in_place'].enable()
        else:
            key_ele_map['opt::rename_in_place'].enable()
            key_ele_map['opt::no_album_move'].enable()

    # endregion

    # region Update Methods

    def update(self, key_ele_map: Mapping[str, CheckBox | Element], no_album_move: bool = None):
        self.update_option_states(key_ele_map)
        self.maybe_update_new_album_path()
        if no_album_move is not None:
            self.update_path_ele_visibility(no_album_move)

    def maybe_update_new_album_path(self):
        if new_album_path := self.new_album_path:
            new_album_path = new_album_path.as_posix()
        else:
            new_album_path = ''

        self.path_diff_eles[0].rows[-1].elements[-1].update(new_album_path)  # This updated the rename element value

    def update_path_ele_visibility(self, no_album_move: bool):
        rename_ele, no_change_ele = self.path_diff_eles
        if no_album_move:
            rename_ele.hide()
            no_change_ele.show()
        else:
            rename_ele.show()
            no_change_ele.hide()

    # endregion


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
            yield [Text('File:'), IText(old_name, size=(50, 1)), Text('(no change)')]

    def build_tag_diff(self) -> Layout:
        title_case = self.options['title_case']
        old_data = self.old_info.to_dict(title_case, genres_as_set=True)
        new_data = self.new_info.to_dict(title_case, genres_as_set=True)
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

    def build_genre_diff(self, old_vals: set[str], new_val: set[str]) -> Layout:
        # old genres are from unmodified TrackInfo, which already includes album genres
        old_alb_vals, new_alb_vals = self.genres  # new will already include old if not repl_genres

        new_vals = (new_val | new_alb_vals) if new_val else new_alb_vals.copy()
        if not self.options['repl_genres']:
            new_vals.update(old_vals)

        # if (new_vals != new_alb_vals) or (old_vals != new_vals):
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
            if not value:
                return Text('<removed>', size=(45, 1))
            kwargs = {'size': (45, len(value)), 'pad': (5, 0), 'border': 2}
            return ListBox(value, default=value, disabled=True, scroll_y=False, **kwargs)
        case _:
            return IText(value, size=(45, 1), link=key.startswith('wiki_') or None)


def get_a_to_b(label: str, old_val: PathLike, new_val: PathLike, split: bool = None) -> Layout:
    old_ele, split_old = _diff_ele(old_val, split)
    new_ele, split_new = _diff_ele(new_val, split, offset=3)
    if split_old or split_new:
        yield [label_ele(label), old_ele]
        yield [Spacer(size=((len(label) + 1) * 7, 1)), Text('\u2794', font=('Helvetica', 15), size=(2, 1)), new_ele]
    else:
        yield [label_ele(label), old_ele, Text('\u2794', font=('Helvetica', 15), size=(2, 1)), new_ele]


def _diff_ele(value: PathLike, split: bool = None, offset: int = 0) -> tuple[Text, bool]:
    if isinstance(value, Path):
        value = value.as_posix()
    elif value is None:
        value = ''

    if split is None:
        split = len(value) > 50
    return IText(value, size=((150 - offset) if split else 50, 1)), split


def _str_set(values: StrOrStrs) -> set[str]:
    if isinstance(values, str):
        return {values}
    return set(values)


def label_ele(text: str, size: XY = (15, 1), **kwargs) -> Text:
    return Text(text.replace('_', ' ').title(), size=size, **kwargs)
