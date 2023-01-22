"""

"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Iterator, Collection, Optional, Sequence

from ds_tools.caching.decorators import cached_property
from tk_gui.elements import Element, ListBox, CheckBox, Image, Combo, HorizontalSeparator
from tk_gui.elements.buttons import Button, ButtonAction
from tk_gui.elements.frame import InteractiveFrame, Frame, RowFrame
from tk_gui.elements.rating import Rating
from tk_gui.elements.text import Multiline, Text, Input
from tk_gui.popups import popup_ok

from music.common.disco_entry import DiscoEntryType
from music.files.exceptions import TagNotFound
from music.files.track.track import SongFile
from music.manager.update import TrackInfo, AlbumInfo
from ..utils import AlbumIdentifier, TrackIdentifier, get_album_info, get_album_dir, get_track_info, get_track_file
from .images import icon_cache, get_raw_cover_image
from .list_box import EditableListBox

if TYPE_CHECKING:
    from tk_gui.typing import Layout, Bool, XY

__all__ = ['AlbumInfoFrame', 'TrackInfoFrame']
log = logging.getLogger(__name__)

ValueEle = Text | Multiline | Rating | ListBox
_multiple_covers_warned = set()


class ButtonRow(RowFrame):
    elements = None  # Necessary to satisfy the ABC

    def __init__(self, buttons: Sequence[Button], **kwargs):
        super().__init__(side='t', **kwargs)
        self.elements = buttons


class AlbumInfoFrame(InteractiveFrame):
    album_info: AlbumInfo

    def __init__(self, album: AlbumIdentifier, cover_size: XY = (250, 250), **kwargs):
        self.album_info = get_album_info(album)
        self.album_dir = get_album_dir(album)
        super().__init__(**kwargs)
        self.cover_size = cover_size

    def get_custom_layout(self) -> Layout:
        yield from self.build_meta_rows()
        width, height = self.cover_size
        cf_size = (width + 10, height + 10)  # TODO: Need some way to force it - is an invisible image really necessary?
        yield [Frame([[self.cover_image_thumbnail]], size=cf_size), Frame([*self.build_tag_rows()])]
        yield [HorizontalSeparator()]
        buttons = list(self.buttons.values())
        yield [ButtonRow(buttons[:4])]
        yield [ButtonRow(buttons[4:7])]
        yield [ButtonRow(buttons[-1:])]

    # region Cover Image

    @cached_property
    def _cover_images_raw(self) -> set[bytes]:
        images = set()
        missing = 0
        for track in self.album_info.tracks.values():
            try:
                if image := get_raw_cover_image(SongFile(track.path), True):
                    images.add(image)
            except TagNotFound:
                missing += 1

        n_img = len(images)
        messages = []
        if missing:
            messages.append(f'cover images were missing for {missing} tracks')
        if not n_img and not missing:
            messages.append('no cover images were found')
        elif n_img > 1:
            messages.append(f'{n_img} cover images were found')

        if messages and self.album_info.path not in _multiple_covers_warned:
            _multiple_covers_warned.add(self.album_info.path)
            popup_ok(f'Warning: {" and ".join(messages)} for {self.album_info}', keep_on_top=True)

        return images

    @cached_property
    def _cover_image_raw(self) -> Optional[bytes]:
        if (images := self._cover_images_raw) and len(images) == 1:
            return next(iter(images))
        return None

    @property
    def cover_image_thumbnail(self) -> Image:
        # TODO: Right-click menu to add/replace the image
        image = icon_cache.image_or_placeholder(self._cover_image_raw, self.cover_size)
        return Image(image=image, size=self.cover_size, popup=True, popup_title=f'Album Cover: {self.album_info.name}')

    # endregion

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
        for key, value in self.album_info.to_dict().items():
            if key == 'tracks':
                continue
            if tooltip := tooltips.get(key):
                kwargs = {'tooltip': tooltip}
            else:
                kwargs = {}

            key_ele = Text(key.replace('_', ' ').title(), size=(15, 1), **kwargs)
            if key == 'type':
                types = [de.real_name for de in DiscoEntryType]
                if value and value not in types:
                    types.append(value)
                val_ele = Combo(types, value, size=(48, None), disabled=disabled)
            elif key == 'genre':
                kwargs |= {'size': (50, len(value)), 'pad': (5, 0), 'border': 2}
                val_ele = ListBox(value, default=value, disabled=disabled, scroll_y=False, **kwargs)
            elif key in {'mp4', 'solo_of_group'}:
                kwargs['disabled'] = True if key == 'mp4' else disabled
                val_ele = CheckBox('', default=value, pad=(0, 0), **kwargs)
            else:
                if key.startswith('wiki_'):
                    kwargs['link'] = True
                if value is None:
                    value = ''
                val_ele = Input(value, size=(50, 1), disabled=disabled, **kwargs)

            yield [key_ele, val_ele]

    @cached_property
    def buttons(self) -> dict[str, Button]:
        kwargs = {'size': (18, 1), 'borderwidth': 3, 'action': ButtonAction.BIND_EVENT}
        open_button = Button(
            '\U0001f5c1',
            key='open',
            font=('Helvetica', 20),
            size=(10, 1),
            tooltip='Open',
            borderwidth=3,
            action=ButtonAction.BIND_EVENT,
        )
        return {
            'Clean & Add BPM': Button('Clean & Add BPM', key='clean_and_add_bpm', **kwargs),
            'View All Tags': Button('View All Tags', key='view_all_tags', **kwargs),
            'Edit': Button('Edit', key='edit_album', **kwargs),
            'Wiki Update': Button('Wiki Update', key='wiki_update', **kwargs),
            #
            'Sync Ratings From...': Button('Sync Ratings From...', key='sync_ratings_from', **kwargs),
            'Sync Ratings To...': Button('Sync Ratings To...', key='sync_ratings_to', **kwargs),
            'Copy Tags From...': Button('Copy Tags From...', key='copy_tags_from', **kwargs),
            #
            'Open': open_button,
        }


class TrackInfoFrame(InteractiveFrame):
    track_info: TrackInfo
    song_file: SongFile
    show_cover: Bool = False

    def __init__(self, track: TrackIdentifier, **kwargs):
        self.track_info = get_track_info(track)
        self.song_file = get_track_file(track)
        super().__init__(**kwargs)

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

        disabled = self.disabled
        data = self.track_info.to_dict()
        for key in fields:
            key_ele = Text(key.replace('_', ' ').title(), size=(6, 1))
            if key == 'genre':
                add_prompt = f'Enter a new {key} value to add to {self.track_info.title!r}'
                val_ele = EditableListBox(
                    data[key], add_title=f'Add {key}', add_prompt=add_prompt, list_width=40, disabled=disabled
                )
            elif key == 'rating':
                val_ele = Rating(data[key], show_value=True, pad=(0, 0), disabled=disabled)
            else:
                val_ele = Input(data[key], size=(50, 1), disabled=disabled)

            yield [key_ele, val_ele]
