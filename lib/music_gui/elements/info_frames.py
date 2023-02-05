"""

"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Iterator, Collection, Any

from ds_tools.caching.decorators import cached_property
from ds_tools.output.formatting import ordinal_suffix

from tk_gui.elements import Element, ListBox, CheckBox, Image, Combo, HorizontalSeparator
from tk_gui.elements.buttons import Button, EventButton as EButton
from tk_gui.elements.frame import InteractiveFrame, Frame, BasicRowFrame
from tk_gui.elements.rating import Rating
from tk_gui.elements.text import Multiline, Text, Input
from tk_gui.options import GuiOptions

from music.common.disco_entry import DiscoEntryType
from music.files import AlbumDir, SongFile
from music.manager.update import TrackInfo, AlbumInfo
from ..utils import AlbumIdentifier, TrackIdentifier, get_album_info, get_album_dir, get_track_info, get_track_file
from ..utils import zip_maps
from .images import AlbumCoverImageBuilder
from .list_box import EditableListBox

if TYPE_CHECKING:
    from tk_gui.typing import Layout, Bool, XY, PathLike
    from music.typing import StrOrStrs

__all__ = ['AlbumInfoFrame', 'TrackInfoFrame']
log = logging.getLogger(__name__)

ValueEle = Text | Multiline | Rating | ListBox | Combo | EditableListBox | Input
LRG_FONT = ('Helvetica', 20)


# region Album / Track Info Frames


class TagModMixin:
    _tag_vals_and_eles: dict[str, tuple[Any, ValueEle]]

    def get_modified(self) -> dict[str, tuple[Any, Any]]:
        modified = {}
        for key, (original_val, val_ele) in self._tag_vals_and_eles.items():
            if (value := val_ele.value) != original_val:
                modified[key] = (original_val, value)
        return modified


class TagFrame(InteractiveFrame):
    def enable(self):
        if not self.disabled:
            return

        for row in self.rows:
            for ele in row.elements:
                try:
                    if ele.key == 'mp4':  # Read-only
                        continue
                except AttributeError:
                    pass
                try:
                    ele.enable()  # noqa
                except AttributeError:
                    pass

        self.disabled = False


class AlbumInfoFrame(TagModMixin, InteractiveFrame):
    album_info: AlbumInfo

    def __init__(self, album: AlbumIdentifier, cover_size: XY = (250, 250), **kwargs):
        super().__init__(**kwargs)
        self.album_info = get_album_info(album)
        self.album_dir = get_album_dir(album)
        self.cover_size = cover_size
        self._tag_vals_and_eles = {}

    # region Layout Generation

    def get_custom_layout(self) -> Layout:
        yield from self.build_meta_rows()
        # TODO: Right-click menu to add/replace the image
        cover_image = AlbumCoverImageBuilder(self.album_info, self.cover_size).make_thumbnail_frame()
        yield [cover_image, TagFrame([*self.build_tag_rows()], disabled=self.disabled)]
        yield [HorizontalSeparator()]
        yield from self.build_buttons()

    def build_meta_rows(self):
        data = {'bitrate_str': set(), 'sample_rate_str': set(), 'bits_per_sample': set()}
        for track in self.album_dir:
            info = track.info
            for key, values in data.items():
                if value := info[key]:
                    values.add(str(value))

        data = {key: ' / '.join(sorted(values)) for key, values in data.items()}
        yield [
            Text('Bitrate:'), Text(data['bitrate_str'], size=(18, 1), use_input_style=True),
            Text('Sample Rate:'), Text(data['sample_rate_str'], size=(18, 1), use_input_style=True),
            Text('Bit Depth:'), Text(data['bits_per_sample'], size=(18, 1), use_input_style=True),
        ]
        yield [HorizontalSeparator()]

    def build_tag_rows(self):
        tooltips = {
            'name': 'The name that was / should be used for the album directory',
            'parent': 'The name that was / should be used for the artist directory',
            'singer': 'Solo singer of a group, when the album should be sorted under their group',
            'solo_of_group': 'Whether the singer is a soloist',
        }
        disabled = self.disabled
        for key, value in self.album_info.to_dict(skip={'tracks'}, genres_as_set=True).items():
            if tooltip := tooltips.get(key):
                kwargs = {'tooltip': tooltip}
            else:
                kwargs = {}

            key_ele = label_ele(key, **kwargs)
            if key == 'type':
                types = [de.real_name for de in DiscoEntryType]
                if value and value not in types:
                    types.append(value)
                val_ele = Combo(
                    types, value, size=(48, None), disabled=disabled, key=key, change_cb=self._update_numbered_type
                )
            elif key == 'genre':
                val_ele = _genre_list_box(value, self.album_info, disabled, key=key)
            elif key in {'mp4', 'solo_of_group'}:
                kwargs['disabled'] = True if key == 'mp4' else disabled
                val_ele = CheckBox('', default=value, pad=(0, 0), key=key, **kwargs)
            else:
                if key.startswith('wiki_'):
                    kwargs['link'] = True
                elif key == 'number':
                    kwargs['change_cb'] = self._update_numbered_type
                value = _normalize_input_value(value)
                val_ele = Input(value, size=(50, 1), disabled=disabled, key=key, **kwargs)

            self._tag_vals_and_eles[key] = (value, val_ele)
            yield [key_ele, val_ele]

    def build_buttons(self) -> Layout:
        # These frames need to be in the same row for them to occupy the same space when visible
        yield [self.view_buttons_frame, self.edit_buttons_frame]

    @cached_property
    def view_buttons_frame(self) -> Frame:
        kwargs = {'size': (18, 1), 'borderwidth': 3}
        rows = [
            [
                EButton('Clean & Add BPM', key='clean_and_add_bpm', **kwargs),
                EButton('View All Tags', key='view_all_tags', **kwargs),
                EButton('Edit', key='edit_album', **kwargs),
                EButton('Wiki Update', key='wiki_update', **kwargs),
            ],
            [
                EButton('Sync Ratings From...', key='sync_ratings_from', **kwargs),
                EButton('Sync Ratings To...', key='sync_ratings_to', **kwargs),
                EButton('Copy Tags From...', key='copy_tags_from', **kwargs),
            ],
            [EButton('\U0001f5c1', key='open', font=LRG_FONT, size=(10, 1), tooltip='Open', borderwidth=3)],
        ]
        return Frame([[BasicRowFrame(row, side='t')] for row in rows], visible=self.disabled, side='t')

    @cached_property
    def edit_buttons_frame(self) -> BasicRowFrame:
        kwargs = {'size': (18, 1), 'borderwidth': 3}
        row = [EButton('Review & Save Changes', key='save', **kwargs), EButton('Cancel', key='cancel', **kwargs)]
        return BasicRowFrame(row, side='t', anchor='c', visible=not self.disabled)

    # endregion

    # region Event Handling

    def enable(self):
        if not self.disabled:
            return
        super().enable()
        self.view_buttons_frame.hide()
        self.edit_buttons_frame.show()

    def disable(self):
        if self.disabled:
            return
        super().disable()
        self.edit_buttons_frame.hide()
        self.view_buttons_frame.show()

    def _update_numbered_type(self, var_name, unknown, action):
        # Registered as a change_cb for `type` and `number`
        type_val = DiscoEntryType(self._tag_vals_and_eles['type'][1].value)
        if type_val == DiscoEntryType.UNKNOWN:
            return
        num_ele = self._tag_vals_and_eles['number'][1]
        try:
            num_val = int(num_ele.value.strip())
        except (TypeError, ValueError, AttributeError):
            # TODO: Mark num_ele as invalid if it has a value
            return

        num_type_ele: Input = self._tag_vals_and_eles['numbered_type'][1]
        num_type_ele.update(f'{num_val}{ordinal_suffix(num_val)} {type_val.real_name}')

    # endregion


class TrackInfoFrame(TagModMixin, InteractiveFrame):
    track_info: TrackInfo
    song_file: SongFile
    show_cover: Bool = False

    def __init__(self, track: TrackIdentifier, **kwargs):
        super().__init__(**kwargs)
        self.track_info = get_track_info(track)
        self.song_file = get_track_file(track)
        self._tag_vals_and_eles = {}

    @cached_property
    def path_str(self) -> str:
        return self.track_info.path.as_posix()

    @cached_property
    def file_name(self) -> str:
        return self.track_info.path.name

    def get_custom_layout(self) -> Layout:
        yield from self.build_meta_rows()
        yield from self.build_info_rows()

    def build_meta_rows(self) -> Iterator[list[Element]]:
        yield [Text('File:', size=(6, 1)), Text(self.file_name, size=(50, 1), use_input_style=True)]
        sf = self.song_file
        kwargs = {'use_input_style': True}
        yield [
            Text('Length:', size=(6, 1)), Text(sf.length_str, size=(10, 1), **kwargs),
            Text('Type:'), Text(sf.tag_version, size=(20, 1), **kwargs),
        ]

    def build_info_rows(self, keys: Collection[str] = None) -> Iterator[list[Element]]:
        fields = ['artist', 'title', 'name', 'genre', 'disk', 'num', 'rating']
        if keys:
            fields = [f for f in fields if f not in keys]

        track_info, disabled = self.track_info, self.disabled
        for key in fields:
            if key == 'genre':
                value = track_info.genre_set.difference(track_info.album.genre_set)
                val_ele = _genre_list_box(value, track_info, disabled)
            elif key == 'rating':
                if (value := track_info[key]) is None:
                    value = 0
                val_ele = Rating(value, show_value=True, pad=(0, 0), disabled=disabled)
            else:
                value = _normalize_input_value(track_info[key])
                val_ele = Input(value, size=(50, 1), disabled=disabled)

            self._tag_vals_and_eles[key] = (value, val_ele)
            yield [label_ele(key, size=(6, 1)), val_ele]


# endregion

# region Album / Track Diff Frames


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

    def build_header(self) -> Layout:
        options_frame = self.options.as_frame('apply_changes', change_cb=self.update_options)
        # TODO: Center options frame, maybe tweak "submit" button location?
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
            # TODO: Arrow is cut off on right side
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
        super().__init__(**kwargs)
        self.old_info = old_info
        self.new_info = new_info
        self.song_file = song_file or get_track_file(old_info)
        self.options = options
        self.genres = genres

    def get_custom_layout(self) -> Layout:
        yield [Text()]
        # TODO: Make separator width/length consistent
        yield [HorizontalSeparator()]
        yield from self.build_name_diff()
        yield from self.build_tag_diff()

    def build_name_diff(self) -> Layout:
        old_name = self.song_file.path.name
        new_name = self.new_info.expected_name(self.song_file)
        if old_name != new_name:
            yield from get_a_to_b('File Rename:', old_name, new_name)
        else:
            # TODO: Make field width consistent
            yield [Text('File:'), Text(old_name, use_input_style=True), Text('(no change)')]

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


def _genre_list_box(genres: Collection[str], info: TrackInfo | AlbumInfo, disabled: bool, **kwargs) -> EditableListBox:
    kwargs.setdefault('add_title', 'Add genre')
    kwargs.setdefault('add_prompt', f'Enter a new genre value to add to {info.title!r}')
    kwargs.setdefault('list_width', 40)
    return EditableListBox(sorted(genres), disabled=disabled, val_type=set, **kwargs)


def _normalize_input_value(value) -> str:
    if value is None:
        value = ''
    elif not isinstance(value, str):
        value = str(value)
    return value


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
        yield [Image(size=(len(label) * 7, 1)), Text('\u2794', font=('Helvetica', 15)), new_ele]
    else:
        yield [Text(label), old_ele, Text('\u2794', font=('Helvetica', 15)), new_ele]


def _diff_ele(value: PathLike) -> tuple[Text, int]:
    if isinstance(value, Path):
        value = value.as_posix()
    kwargs = {'use_input_style': True}
    if (val_len := len(value)) > 50:
        kwargs['size'] = (val_len, 1)
    return Text(value, **kwargs), val_len


def _str_set(values: StrOrStrs) -> set[str]:
    if isinstance(values, str):
        return {values}
    return set(values)


def label_ele(text: str, size: XY = (15, 1), **kwargs) -> Text:
    return Text(text.replace('_', ' ').title(), size=size, **kwargs)
