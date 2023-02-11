"""

"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Iterator, Collection, Any

from ds_tools.caching.decorators import cached_property
from ds_tools.output.formatting import ordinal_suffix

from tk_gui.elements import Element, ListBox, CheckBox, Combo, HorizontalSeparator
from tk_gui.elements.buttons import EventButton as EButton
from tk_gui.elements.frame import InteractiveFrame, Frame, BasicRowFrame
from tk_gui.elements.rating import Rating
from tk_gui.elements.text import Multiline, Text, Input

from music.common.disco_entry import DiscoEntryType
from music.files import SongFile
from music.manager.update import TrackInfo, AlbumInfo
from ..utils import AlbumIdentifier, TrackIdentifier, get_album_info, get_album_dir, get_track_info, get_track_file
from .images import AlbumCoverImageBuilder
from .list_box import EditableListBox

if TYPE_CHECKING:
    from tk_gui.typing import Layout, Bool, XY

__all__ = ['AlbumInfoFrame', 'TrackInfoFrame']
log = logging.getLogger(__name__)

ValueEle = Text | Multiline | Rating | ListBox | Combo | EditableListBox | Input
LRG_FONT = ('Helvetica', 20)


class TagModMixin:
    _tag_vals_and_eles: dict[str, tuple[Any, ValueEle]]

    def _iter_changes(self) -> Iterator[tuple[str, ValueEle, Any, Any]]:
        for key, (original_val, val_ele) in self._tag_vals_and_eles.items():
            if (value := val_ele.value) != original_val:
                yield key, val_ele, original_val, value

    def reset_tag_values(self):
        for key, val_ele, original_val, value in self._iter_changes():
            match val_ele:
                case ListBox() | EditableListBox():
                    val_ele.update(choices=original_val, replace=True, select=True)
                case _:  # Input() | Text() | CheckBox() | Combo() | Rating()
                    val_ele.update(original_val)

    def get_modified(self) -> dict[str, tuple[Any, Any]]:
        return {key: (original_val, value) for key, val_ele, original_val, value in self._iter_changes()}


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


def label_ele(text: str, size: XY = (15, 1), **kwargs) -> Text:
    return Text(text.replace('_', ' ').title(), size=size, **kwargs)


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
