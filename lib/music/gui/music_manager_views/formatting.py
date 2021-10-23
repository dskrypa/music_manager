"""
Album / track formatting helper functions.

:author: Doug Skrypa
"""

import re
from collections import defaultdict
from concurrent import futures
from functools import cached_property
from io import BytesIO
from itertools import count
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Any, Iterator, Collection

from PIL import Image as ImageModule
from PIL.Image import Image as PILImage
from PySimpleGUI import Text, Image, Multiline, Column, Element, Checkbox, Listbox, Button, Combo
from PySimpleGUI import HorizontalSeparator, WRITE_ONLY_KEY
from requests import RequestException

from ds_tools.fs.paths import get_user_cache_dir
from ds_tools.images.utils import ImageType
from wiki_nodes.http import MediaWikiClient
from ...common.disco_entry import DiscoEntryType
from ...common.ratings import stars_from_256
from ...files.album import AlbumDir
from ...files.exceptions import TagNotFound
from ...files.track.track import SongFile
from ...manager.update import AlbumInfo, TrackInfo
from ..base_view import Layout, EleBinds, GuiView
from ..elements import ExtendedImage, ExtInput, SearchMenu, Rating
from ..popups.simple import popup_ok
from ..popups.text import popup_error
from ..utils import resize_text_column
from .utils import label_and_val_key, label_and_diff_keys, get_a_to_b

if TYPE_CHECKING:
    from .album import AlbumView

__all__ = ['TrackFormatter', 'AlbumFormatter']
_multiple_covers_warned = set()
ICONS_DIR = Path(__file__).resolve().parents[4].joinpath('icons')


class AlbumFormatter:
    def __init__(self, view: 'GuiView', album_dir: AlbumDir, cover_size: tuple[int, int] = (250, 250)):
        self.view = view
        self.album_dir = album_dir
        self._src_album_info = AlbumInfo.from_album_dir(album_dir)
        self._new_album_info = None
        self.cover_size = cover_size
        self._images = None  # type: Optional[dict[str, bytes]]

    @property
    def log(self):
        return self.view.log

    @property
    def album_info(self) -> AlbumInfo:
        if self._new_album_info is None:
            return self._src_album_info
        return self._new_album_info

    @album_info.setter
    def album_info(self, value: AlbumInfo):
        self._new_album_info = value
        for path, track in self.track_formatters.items():
            try:
                track.info = value.tracks[path]
            except KeyError:
                self.log.warning(f'No track match found for {path=}')
                value.tracks[path] = track.info

    def reset_changes(self):
        self._new_album_info = None
        for track in self:
            track._new_info = None

    @cached_property
    def track_formatters(self) -> dict[str, 'TrackFormatter']:
        formatters = {}
        for track in self.album_dir:
            path = track.path.as_posix()
            info = self.album_info.tracks[path]
            formatters[path] = TrackFormatter(self, track, info, self.cover_size)
        return formatters

    def __iter__(self) -> Iterator['TrackFormatter']:
        yield from self.track_formatters.values()

    # region Wiki methods

    @property
    def wiki_client(self) -> Optional[MediaWikiClient]:
        if wiki_album_url := self.album_info.wiki_album:
            if wiki_album_url.startswith('https://music.bugs.co.kr'):
                return None
            return MediaWikiClient(wiki_album_url, nopath=True)
        return None

    @property
    def wiki_image_urls(self) -> Optional[dict[str, str]]:
        if client := self.wiki_client:
            try:
                page = client.get_page(client.article_url_to_title(self.album_info.wiki_album))
            except RequestException as e:
                self.log.error(f'Error retrieving images from {self.album_info.wiki_album}: {e}')
                return None
            else:
                if image_titles := client.get_page_image_titles(page.title)[page.title]:
                    self.log.debug(f'Found {len(image_titles)} images on page={page.title!r}: {image_titles}')
                    return client.get_image_urls(image_titles)
        return None

    def _get_wiki_cover_images(self):
        urls = self.wiki_image_urls
        self._images = {}
        with futures.ThreadPoolExecutor(max_workers=4) as executor:
            future_objs = {executor.submit(self.wiki_client.get_image, title): title for title in urls}
            for future in futures.as_completed(future_objs):
                title = future_objs[future]
                try:
                    self._images[title] = future.result()
                except Exception as e:
                    self.log.error(f'Error retrieving image={title!r}: {e}')

    def get_wiki_cover_images(self):
        if self._images is None:
            GuiView.start_task(self._get_wiki_cover_images, message='Downloading images...')
        return self._images

    def get_wiki_cover_choice(self) -> Optional[Path]:
        from ..popups.choose_image import choose_image

        if images := self.get_wiki_cover_images():
            if title := choose_image(images):
                cover_dir = Path(get_user_cache_dir('music_manager/cover_art'))
                name = title.split(':', 1)[1] if title.lower().startswith('file:') else title
                path = cover_dir.joinpath(name)
                if not path.is_file():
                    img_data = self.wiki_client.get_image(title)
                    with path.open('wb') as f:
                        f.write(img_data)
                return path
        return None

    # endregion

    # region Cover Image methods

    @cached_property
    def _cover_image_count(self):
        return len(set(filter(None, (tb._cover_image_raw for tb in self))))

    def _get_cover_image_obj(self) -> Optional[PILImage]:
        if (image_count := self._cover_image_count) == 1:
            return next(iter(self.track_formatters.values())).cover_image_obj
        elif image_count:
            raise MultipleCoversFound(image_count)
        return None

    @property
    def cover_image_thumbnail(self) -> ExtendedImage:
        if (album_info := self._new_album_info) and album_info.cover_path:
            image = album_info.cover_path
        else:
            try:
                image = self._get_cover_image_obj()
            except MultipleCoversFound as e:
                image = None
                if self.album_dir.path not in _multiple_covers_warned:
                    _multiple_covers_warned.add(self.album_dir.path)
                    popup_ok(f'Warning: found {e.n} cover images for {self.album_dir}', keep_on_top=True)

        return self._make_thumbnail(image, 'img::album::cover-thumb', True)

    def _make_thumbnail(self, image: ImageType, key, can_replace: bool = False, prefix: str = None) -> ExtendedImage:
        prefix = f'{prefix} ' if prefix else ''
        kwargs = dict(size=self.cover_size, key=key, popup_title=f'{prefix}Album Cover: {self.album_info.name}')
        if image is not None:
            if can_replace and self.wiki_image_urls:
                kwargs['right_click_menu'] = ['Image', ['Replace Image']]
        elif can_replace and self.wiki_image_urls:
            kwargs['right_click_menu'] = ['Image', ['Add Image']]
        return ExtendedImage(image or ICONS_DIR.joinpath('x.png'), bind_click=image is not None, **kwargs)

    def get_cover_image_diff(self, new_album_info: AlbumInfo) -> Optional[tuple[Image, Image]]:
        if new_album_info.cover_path:
            try:
                src_pil_image = self._get_cover_image_obj()
            except MultipleCoversFound as e:
                popup_ok(f'Warning: found {e.n} different cover images for {self.album_dir}')
                src_pil_image = None

            src_img_ele = self._make_thumbnail(src_pil_image, 'img::album::cover-src', prefix='Original')
            new_img_ele = self._make_thumbnail(new_album_info.cover_path, 'img::album::cover-new', prefix='New')
            return src_img_ele, new_img_ele
        return None

    # endregion

    def get_album_diff_rows(self, new_album_info: AlbumInfo, title_case: bool = False, add_genre: bool = False):
        rows = []
        new_info_dict = new_album_info.to_dict(title_case)
        for key, src_val in self._src_album_info.to_dict(title_case).items():
            if key == 'tracks':
                continue

            new_val = new_info_dict[key]
            if key == 'genre' and add_genre:
                new_vals = {new_val} if isinstance(new_val, str) else set(new_val)
                new_vals.update(src_val)
                new_val = sorted(new_vals)

            if (src_val or new_val) and src_val != new_val:
                # self.log.debug(f'album: {key} is different: {src_val=!r} != {new_val=!r}')
                label, sep_1, sep_2, src_key, new_key = label_and_diff_keys('album', key)
                src_ele = value_ele(src_val, src_key, True, 45)
                new_ele = value_ele(new_val, new_key, True, 45)
                rows.append([label, sep_1, src_ele, sep_2, new_ele])

        return resize_text_column(rows)

    def get_dest_path(self, new_album_info: AlbumInfo, dest_base_dir: Path = None) -> Optional[Path]:
        try:
            expected_rel_dir = new_album_info.expected_rel_dir
        except AttributeError:
            return None
        dest_base_dir = new_album_info.dest_base_dir(self.album_dir, dest_base_dir)
        return dest_base_dir.joinpath(expected_rel_dir)

    def get_album_data_rows(self, editable: bool = False):
        rows = []
        album_view = self.view.name == 'album'
        text_keys = {'title', 'artist', 'name', 'parent', 'singer'}
        for key, value in self.album_info.to_dict().items():
            if key == 'tracks':
                continue
            disabled = not editable or key == 'mp4'
            key_ele, val_key = label_and_val_key('album', key)
            if key == 'type':
                types = [de.real_name for de in DiscoEntryType]
                if value and value not in types:
                    types.append(value)
                val_ele = Combo(types, value, key=val_key, disabled=disabled)
            else:
                kwargs = {'link': True} if key.startswith('wiki_') else {}
                val_ele = value_ele(value, val_key, disabled, **kwargs)
                if album_view and key in text_keys:
                    add_right_click_text_options(val_ele, val_key, self.view)  # noqa

            rows.append([key_ele, val_ele])

        return resize_text_column(rows)


class MultipleCoversFound(Exception):
    def __init__(self, n: int):
        self.n = n


def add_right_click_text_options(val_ele: ExtInput, val_key: str, view: 'AlbumView'):
    val_ele.right_click_menu.add_option(
        'Flip name parts', val_key, val_ele.flip_name_content_parts, call_with_kwargs=False, event=view._edit_event
    )
    for case in ('title', 'lower', 'upper'):
        val_ele.right_click_menu.add_option(
            f'Change case: {case.title()}', case, val_ele.change_case, call_with_kwargs=False, event=view._edit_event
        )


def value_ele(
    value: Any, val_key: str, disabled: bool, list_width: int = 30, no_add: bool = False, **kwargs
) -> Element:
    if isinstance(value, bool):
        val_ele = Checkbox('', default=value, key=val_key, disabled=disabled, pad=(0, 0), **kwargs)
    elif isinstance(value, list):
        kwargs.setdefault('tooltip', 'Unselected items will not be saved')
        add_button = not no_add and val_key.startswith('val::')
        if not add_button:
            kwargs.setdefault('pad', (6, 0))
        val_ele = Listbox(
            value,
            default_values=value,
            key=val_key,
            disabled=disabled,
            size=(list_width, len(value)),
            no_scrollbar=True,
            select_mode='extended',  # extended, browse, single, multiple
            **kwargs,
        )
        if add_button:
            val_ele = Column(
                [[val_ele, Button('Add...', key=val_key.replace('val::', 'add::', 1), disabled=disabled, pad=(0, 0))]],
                key=f'col::{val_key}',
                pad=(0, 0),
                vertical_alignment='center',
                justification='center',
                expand_y=True,
                expand_x=True,
            )
    else:
        val_ele = ExtInput(value, key=val_key, disabled=disabled, right_click_menu=SearchMenu(), **kwargs)

    return val_ele


class TrackFormatter:
    _title_pat = re.compile(r'^(?:\d+\S?\s+)?(.*?)\.[a-z]{3,4}$', re.IGNORECASE)

    def __init__(
        self,
        album_formatter: AlbumFormatter,
        track: SongFile,
        info: TrackInfo,
        cover_size: tuple[int, int] = (250, 250),
    ):
        self.album_formatter = album_formatter
        self.track = track
        self.cover_size = cover_size
        self._src_info = info
        self._new_info = None

    @property
    def view(self):
        return self.album_formatter.view

    @property
    def log(self):
        return self.album_formatter.view.log

    @property
    def info(self):
        if self._new_info is None:
            return self._src_info
        return self._new_info

    @info.setter
    def info(self, value: TrackInfo):
        self._new_info = value

    # region Track Image methods

    @cached_property
    def _cover_image_raw(self) -> Optional[bytes]:
        try:
            return self.track.get_cover_data()[0]
        except TagNotFound as e:
            self.log.warning(e)
            return None
        except Exception:
            self.log.error(f'Unable to load cover image for {self.track}', exc_info=True)
            return None

    @cached_property
    def cover_image_obj(self) -> Optional['PILImage']:
        if (data := self._cover_image_raw) is not None:
            return ImageModule.open(BytesIO(data))
        return None

    @property
    def cover_image_thumbnail(self) -> Image:
        return ExtendedImage(
            image=self.cover_image_obj,
            size=self.cover_size,
            key=f'img::{self.path_str}::cover-thumb',
            popup_title=f'Track Album Cover: {self.file_name}'
        )

    # endregion

    @cached_property
    def path_str(self) -> str:
        return self.track.path.as_posix()

    @cached_property
    def file_name(self) -> str:
        return self.track.path.name

    def key_for(self, type: str, field: str, suffix: str = None):
        return f'{type}::{self.path_str}::{field}::{suffix}' if suffix else f'{type}::{self.path_str}::{field}'

    def get_tag_rows(self, editable: bool = True) -> tuple[Layout, EleBinds]:
        rows = []
        ele_binds = {}
        nums = defaultdict(count)
        common_binds = {'<Button-1>': ':::row_clicked', '<Shift-Button-1>': ':::tag_clicked'}

        for trunc_id, tag_id, tag_name, disp_name, val in self.track.iter_tag_id_name_values():
            if disp_name == 'Album Cover':
                continue

            # self.log.debug(f'Making tag row for {tag_id=} {tag_name=} {disp_name=} {val=}')
            if n := next(nums[tag_id]):
                tag_id = f'{tag_id}--{n}'

            key_ele = Text(disp_name, key=self.key_for('tag', tag_id, WRITE_ONLY_KEY), tooltip=tag_id)
            sel_box = Checkbox('', key=self.key_for('del', tag_id), visible=editable, enable_events=True)
            tooltip = f'Toggle all {tag_id} tags with Shift+Click'
            val_key = self.key_for('val', tag_id)

            if disp_name == 'Lyrics':
                val_ele = Multiline(val, size=(45, 4), key=val_key, disabled=True, tooltip='Pop out with ctrl + click')
                rows.append([key_ele, sel_box, val_ele])
                ele_binds[val_key] = {'<Control-Button-1>': ':::pop_out', **common_binds}
            elif disp_name == 'Rating':
                try:
                    rating = stars_from_256(int(val), 10)
                except (ValueError, TypeError):
                    val_ele = value_ele(val, val_key, True, no_add=True, list_width=45, tooltip=tooltip)
                    rows.append([key_ele, sel_box, val_ele])
                else:
                    row = [
                        key_ele,
                        sel_box,
                        Rating(rating, key=val_key, show_value=True, disabled=True, tooltip=tooltip, pad=(0, 0)),
                    ]
                    rows.append(row)
                ele_binds[val_key] = common_binds.copy()
            else:
                val_ele = value_ele(val, val_key, True, no_add=True, list_width=45, tooltip=tooltip)
                rows.append([key_ele, sel_box, val_ele])
                ele_binds[val_key] = common_binds.copy()

        return resize_text_column(rows), ele_binds

    def _rating_row(self, key: str, value, editable: bool = False, suffix: str = None):
        key_ele = Text(key.replace('_', ' ').title(), key=self.key_for('tag', key, suffix) + WRITE_ONLY_KEY)
        row = [
            key_ele,
            Rating(value, key=self.key_for('val', key, suffix), show_value=True, pad=(0, 0), disabled=not editable),
        ]
        return row

    def get_info_rows(self, editable: bool = True, keys: Collection[str] = None):
        rows = []
        album_view = self.view.name == 'album'
        text_keys = {'title', 'artist', 'name'}
        for key, value in self.info.to_dict().items():
            if keys and key not in keys:
                continue
            elif key == 'rating':
                rows.append(self._rating_row(key, value, editable))
            else:
                key_ele = Text(key.replace('_', ' ').title(), key=self.key_for('tag', key, WRITE_ONLY_KEY))
                val_key = self.key_for('val', key)
                val_ele = value_ele(value, val_key, not editable)
                if album_view and key in text_keys:
                    add_right_click_text_options(val_ele, val_key, self.album_formatter.view)  # noqa
                rows.append([key_ele, val_ele])

        return resize_text_column(rows)

    def get_sync_rows(self):
        row = [
            Text('Num', key=self.key_for('tag', 'num', WRITE_ONLY_KEY)),
            ExtInput(self.info.num, key=self.key_for('val', 'num'), disabled=True, size=(5, 1)),
            Text('Title', key=self.key_for('tag', 'title', WRITE_ONLY_KEY)),
            ExtInput(self.info.title, key=self.key_for('val', 'title'), disabled=True),
        ]
        rows = [row, self._rating_row('rating', self.info.rating, False)]
        return resize_text_column(rows)

    def get_diff_rows(self, new_track_info: TrackInfo, title_case: bool = False, add_genre: bool = False):
        album_src_genres = set(self.album_formatter._src_album_info.genre_list(title_case))
        album_new_genres = set(new_track_info.album.genre_list(title_case))
        if add_genre:
            album_new_genres.update(album_src_genres)

        rows = []
        new_info_dict = new_track_info.to_dict(title_case)
        for key, src_val in self._src_info.to_dict(title_case).items():
            new_val = new_info_dict[key]
            skip = False
            if key == 'genre':
                if new_val:
                    new_vals = {new_val} if isinstance(new_val, str) else set(new_val)
                    new_vals.update(album_new_genres)
                else:
                    new_vals = album_new_genres.copy()
                if add_genre:
                    new_vals.update(src_val)

                skip = set(src_val) == album_src_genres and new_vals == album_new_genres
                new_val = sorted(new_vals)

            if not skip and (src_val or new_val) and src_val != new_val:
                # self.log.debug(f'{self.path_str}: {key} is different: {src_val=!r} != {new_val=!r}')
                label, sep_1, sep_2, src_key, new_key = label_and_diff_keys(self.path_str, key)
                if key == 'rating':
                    src_row = self._rating_row(key, src_val, suffix='src')[1:]
                    new_row = self._rating_row(key, new_val, suffix='new')[1:]
                    rows.append([label, sep_1, *src_row, sep_2, *new_row])
                else:
                    src_ele = value_ele(src_val, src_key, True, 45)
                    new_ele = value_ele(new_val, new_key, True, 45)
                    rows.append([label, sep_1, src_ele, sep_2, new_ele])

        return resize_text_column(rows)

    def get_basic_info_row(self):
        track = self.track
        tag_version = f'{track.tag_version} (lossless)' if track.lossless else track.tag_version
        # name_key = self.key_for('val', 'file_name')
        name_ele = ExtInput(track.path.name, size=(50, 1), disabled=True, path=self.path_str)
        if self.view.name == 'album':
            self._add_extract_options(name_ele)

        return [
            Text('File:'), name_ele,
            Text('Length:'), ExtInput(track.length_str, size=(6, 1), disabled=True),
            Text('Type:'), ExtInput(tag_version, size=(20, 1), disabled=True),
        ]

    def get_metadata_row(self):
        info = self.track.info
        row = [
            Text('Bitrate:'), ExtInput(info['bitrate_str'], size=(14, 1), disabled=True),
            Text('Sample Rate:'), ExtInput(info['sample_rate_str'], size=(10, 1), disabled=True),
        ]
        for key in ('encoder', 'codec'):
            if value := info.get(key):
                row.append(Text(f'{key.title()}:'))
                row.append(ExtInput(value, size=(15, 1), disabled=True))
        return row

    def as_info_rows(self, editable: bool = True, keys: Collection[str] = None):
        yield [HorizontalSeparator()]
        yield self.get_basic_info_row()
        yield [Column(self.get_info_rows(editable, keys), key=f'col::{self.path_str}::tags')]

    def as_all_tag_rows(self, editable: bool = True):
        cover = Column([[self.cover_image_thumbnail]], key=f'col::{self.path_str}::cover')
        tag_rows, ele_binds = self.get_tag_rows(editable)
        tags = Column(tag_rows, key=f'col::{self.path_str}::tags')
        layout = [[HorizontalSeparator()], self.get_basic_info_row(), self.get_metadata_row(), [cover, tags]]
        return layout, ele_binds

    def as_diff_rows(self, new_track_info: TrackInfo, title_case: bool = False, add_genre: bool = False):
        yield [HorizontalSeparator()]
        new_name = new_track_info.expected_name(self.track)
        if self.track.path.name != new_name:
            yield from get_a_to_b('File Rename:', self.track.path.name, new_name, self.path_str, 'file_name')
        else:
            yield [
                Text('File:'),
                ExtInput(self.track.path.name, disabled=True, key=f'src::{self.path_str}::file_name'),
                Text('(no change)'),
            ]

        if diff_rows := self.get_diff_rows(new_track_info, title_case, add_genre):
            yield [Column(diff_rows, key=f'col::{self.path_str}::diff')]
        else:
            yield []

    def as_sync_rows(self):
        yield [HorizontalSeparator()]
        yield self.get_basic_info_row()
        yield from self.get_sync_rows()

    # region Tag Extraction

    def _add_extract_options(self, name_ele: ExtInput):
        kwargs = {'call_with_kwargs': False, 'event': self.view._edit_event}  # noqa
        name_ele.right_click_menu.add_option(
            'Extract Track Number & Title', name_ele, self._extract_track_parts, **kwargs
        )
        name_ele.right_click_menu.add_option('Extract Track Number', name_ele, self._extract_track_num, **kwargs)
        name_ele.right_click_menu.add_option('Extract Track Title', name_ele, self._extract_track_title, **kwargs)

    def _extract_track_parts(self, name_ele: ExtInput):
        self._extract_track_num(name_ele)
        self._extract_track_title(name_ele)

    def _extract_track_num(self, name_ele: ExtInput):
        num_key = self.key_for('val', 'num')
        try:
            num = int(re.search(r'\d+', name_ele.value).group(0))
        except Exception as e:
            popup_error(f'Unable to find number in value={name_ele.value!r}: {e}')
        else:
            self.view.window[num_key].update(str(num))

    def _extract_track_title(self, name_ele: ExtInput):
        title_key = self.key_for('val', 'title')
        try:
            if m := self._title_pat.match(name_ele.value):
                name = m.group(1).strip()
                if name.lower().endswith('.com') and ' ' in name:
                    name = name.rsplit(maxsplit=1)[0].strip()
                if name.endswith('-'):
                    name = name[:-1].strip()
            else:
                name = None
        except Exception as e:
            popup_error(f'Unable to find name in value={name_ele.value!r}: {e}')
        else:
            if name:
                self.view.window[title_key].update(name)
            else:
                popup_error(f'Unable to find name in value={name_ele.value!r}')

    # endregion
