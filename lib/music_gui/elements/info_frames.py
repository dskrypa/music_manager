"""
AlbumInfo-related frames for the Album view.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Iterator, Collection, Any

from ds_tools.caching.decorators import cached_property
from tk_gui.elements import Element, HorizontalSeparator, Multiline, Text, Input, Image, Spacer
from tk_gui.elements.buttons import Button, EventButton as EButton
from tk_gui.elements.choices import ListBox, CheckBox, Combo
from tk_gui.elements.frame import InteractiveFrame, Frame, BasicRowFrame
from tk_gui.elements.menu import Menu, MenuItem
from tk_gui.elements.rating import Rating
from tk_gui.popups.paths import PickFile

from music.common.disco_entry import DiscoEntryType
from music.files import SongFile
from music.manager.update import TrackInfo, AlbumInfo
from ..utils import AlbumIdentifier, TrackIdentifier, get_album_info, get_album_dir, get_track_info, get_track_file
from .helpers import IText
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
            match val_ele:  # noqa
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
        yield [self.cover_image_frame, TagFrame([*self.build_tag_rows()], disabled=self.disabled)]
        yield [HorizontalSeparator()]
        yield from self.build_buttons()

    def build_meta_rows(self):
        data = {'bitrate_str': set(), 'sample_rate_str': set(), 'bits_per_sample': set()}
        for track in self.album_dir:
            info = track.info
            for key, values in data.items():
                if value := info[key]:
                    values.add(str(value))

        yield [
            Text('Bitrate:'), IText(' / '.join(sorted(data['bitrate_str'])), size=(18, 1)),
            Text('Sample Rate:'), IText(' / '.join(sorted(data['sample_rate_str'])), size=(18, 1)),
            Text('Bit Depth:'), IText(' / '.join(sorted(data['bits_per_sample'])), size=(18, 1)),
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
                kwargs: dict[str, Any] = {'tooltip': tooltip}
            else:
                kwargs = {}

            key_ele = label_ele(key, **kwargs)
            if key == 'type':
                types = [de.real_name for de in DiscoEntryType]
                if value:
                    if isinstance(value, DiscoEntryType):
                        value = value.real_name
                    elif value not in types:
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

    @cached_property
    def cover_image_frame(self) -> Frame:
        class ImageMenu(Menu):
            MenuItem('Replace', callback=self._replace_cover_image, enabled=lambda me: not self.disabled)
            # TODO: Include get_wiki_cover_choice?

        cover_builder = AlbumCoverImageBuilder(self.album_info, self.cover_size)
        return cover_builder.make_thumbnail_frame(right_click_menu=ImageMenu())

    # endregion

    # region Layout Generation - Buttons

    def build_buttons(self) -> Layout:
        # These frames need to be in the same row for them to occupy the same space when visible
        yield [self.view_buttons_frame, self.edit_buttons_frame]

    @cached_property
    def view_buttons_frame(self) -> Frame:
        rows = [[BasicRowFrame(row, side='t')] for row in self._build_view_buttons()]
        return Frame(rows, visible=self.disabled, side='t')

    def _build_view_buttons(self) -> Iterator[list[Button]]:  # noqa
        kwargs = {'size': (18, 1), 'borderwidth': 3}
        yield [
            EButton('Clean & Add BPM', key='clean_and_add_bpm', **kwargs),
            EButton('View All Tags', key='view_all_tags', **kwargs),
            EButton('Edit', key='edit_album', **kwargs),
            EButton('Wiki Update', key='wiki_update', **kwargs),
        ]
        kwargs['size'] = (25, 1)
        # TODO: Handle replacing inferior versions in real destination directory
        yield [
            # EButton('Sync Ratings Between Albums', key='sync_album_ratings', disabled=True, **kwargs),
            EButton('Sort Into Library', key='sort_into_library', **kwargs),
            # EButton('Copy Tags Between Albums', key='copy_album_tags', disabled=True, **kwargs),
        ]

        yield [
            EButton('Copy Tags To Album...', key='copy_src_album_tags', **kwargs),
            EButton('Copy Tags From Album...', key='copy_dst_album_tags', **kwargs),
        ]
        # TODO: Unify the above/below rows / shorten text / merge functionality with the sort view
        yield [
            EButton('Copy Tags To Lib Album...', key='copy_src_lib_album_tags', **kwargs),
            EButton('Copy Tags From Lib Album...', key='copy_dst_lib_album_tags', **kwargs),
        ]

        open_btn = EButton('\U0001f5c1', key='open', font=LRG_FONT, size=(10, 1), tooltip='Open Album', borderwidth=3)
        album_dir = self.album_dir
        # TODO: handle: music.files.exceptions.InvalidAlbumDir: Invalid album dir - contains directories
        if len(album_dir.parent) > 1:
            kwargs = dict(font=LRG_FONT, size=(5, 1), borderwidth=3)
            yield [
                EButton('\u2190', key='prev_dir', **kwargs) if album_dir.has_prev_sibling else Spacer(size=(90, 56)),
                open_btn,
                EButton('\u2192', key='next_dir', **kwargs) if album_dir.has_next_sibling else Spacer(size=(90, 56)),
            ]
        else:
            yield [open_btn]

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
        num_ele: Input = self._tag_vals_and_eles['number'][1]
        value = ''
        try:
            value = num_ele.value.strip()
            num_val = int(value)
        except (TypeError, ValueError, AttributeError):
            num_ele.validated(not value)
            return
        else:
            num_ele.validated(True)

        type_val = DiscoEntryType(self._tag_vals_and_eles['type'][1].value)
        if type_val == DiscoEntryType.UNKNOWN:
            return

        num_type_ele: Input = self._tag_vals_and_eles['numbered_type'][1]
        num_type_ele.update(type_val.format(num_val))

    def _replace_cover_image(self, event=None):
        if self.disabled:
            return

        if path := PickFile(title='Pick new album cover').run():
            cover_path_ele: Input = self._tag_vals_and_eles['cover_path'][1]
            cover_path_ele.update(path.as_posix())
            image_ele: Image = self.cover_image_frame.rows[0].elements[0]
            image_ele.image = path

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
        yield [Text('File:', size=(6, 1)), IText(self.file_name, size=(50, 1))]
        sf = self.song_file
        yield [
            Text('Length:', size=(6, 1)),   IText(sf.length_str, size=(10, 1)),
            Text('Type:'),                  IText(sf.tag_version, size=(20, 1)),
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
