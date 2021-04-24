"""
Album / track formatting helper functions.

:author: Doug Skrypa
"""

from concurrent import futures
from functools import cached_property
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Any, Iterator, Union

from PIL.Image import Image as PILImage
from PySimpleGUI import Text, Image, Multiline, Column, Element, Checkbox, Listbox, Button, Combo
from PySimpleGUI import HorizontalSeparator, VerticalSeparator

from ds_tools.fs.paths import get_user_cache_dir
from wiki_nodes.http import MediaWikiClient
from ...common.disco_entry import DiscoEntryType
from ...constants import typed_tag_name_map
from ...files.album import AlbumDir
from ...files.track.track import SongFile
from ...manager.update import AlbumInfo, TrackInfo
from .base import Layout, EleBinds
from .utils import resize_text_column, label_and_val_key, label_and_diff_keys, get_a_to_b, split_key, DarkInput as Input
from .popups.simple import popup_ok
from .thread_tasks import start_task

if TYPE_CHECKING:
    from .base import GuiView, Event

__all__ = ['TrackBlock', 'AlbumBlock', 'split_key']


class AlbumBlock:
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
    def album_info(self):
        if self._new_album_info is None:
            return self._src_album_info
        return self._new_album_info

    @album_info.setter
    def album_info(self, value: AlbumInfo):
        self._new_album_info = value
        for path, track in self.track_blocks.items():
            track.info = value.tracks[path]

    def reset_changes(self):
        self._new_album_info = None
        for track in self:
            track._new_info = None

    @cached_property
    def track_blocks(self):
        blocks = {}
        for track in self.album_dir:
            path = track.path.as_posix()
            info = self.album_info.tracks[path]
            blocks[path] = TrackBlock(self, track, info, self.cover_size)
        return blocks

    def __iter__(self) -> Iterator['TrackBlock']:
        yield from self.track_blocks.values()

    @cached_property
    def _cover_image_thumbnail(self) -> set[bytes]:
        return set(filter(None, (tb._cover_image_thumbnail for tb in self)))

    @cached_property
    def _cover_image_full(self) -> set[bytes]:
        return set(filter(None, (tb._cover_image_full for tb in self)))

    @property
    def wiki_client(self) -> Optional[MediaWikiClient]:
        if wiki_album_url := self.album_info.wiki_album:
            return MediaWikiClient(wiki_album_url, nopath=True)
        return None

    @property
    def wiki_image_urls(self) -> Optional[dict[str, str]]:
        if client := self.wiki_client:
            page = client.get_page(client.article_url_to_title(self.album_info.wiki_album))
            if image_titles := client.get_page_image_titles(page.title)[page.title]:
                return client.get_image_urls(image_titles)
        return None

    def _get_cover_images(self):
        urls = self.wiki_image_urls
        self._images = {}
        with futures.ThreadPoolExecutor(max_workers=4) as executor:
            future_objs = {executor.submit(self.wiki_client.get_image, title): title for title in urls}
            for future in futures.as_completed(future_objs):
                title = future_objs[future]
                self._images[title] = future.result()

    def get_cover_images(self):
        if self._images is None:
            start_task(self._get_cover_images, message='Downloading images...')
        return self._images

    def get_cover_choice(self) -> Optional[Path]:
        from .popups.choose_image import choose_image

        images = self.get_cover_images()
        if title := choose_image(images):
            cover_dir = Path(get_user_cache_dir('music_manager/cover_art'))
            name = title.split(':', 1)[1] if title.lower().startswith('file:') else title
            path = cover_dir.joinpath(name)
            if not path.is_file():
                img_data = self.wiki_client.get_image(title)
                with path.open('wb') as f:
                    f.write(img_data)
            return path

    def cover_image_thumbnail(self, key: str = 'img::album::cover-thumb', can_replace: bool = True) -> Image:
        cover_images = self._cover_image_thumbnail
        image = None
        if len(cover_images) == 1:
            image = next(iter(cover_images))
        elif cover_images:
            popup_ok(f'Warning: found {len(cover_images)} cover images for {self.album_dir}')
        return self._make_thumnail_image(image, key, can_replace)

    def _make_thumnail_image(self, image: Union[Optional[bytes], 'PILImage'], key, can_replace: bool = False):
        kwargs = dict(size=self.cover_size, key=key)
        if image is not None:
            if isinstance(image, PILImage):
                image = make_thumbnail(image, self.cover_size)

            kwargs['enable_events'] = True
            if can_replace and self.wiki_image_urls:
                kwargs['right_click_menu'] = ['Image', ['Replace Image']]
        return Image(data=image, **kwargs)

    @property
    def cover_image_full_obj(self) -> Optional['PILImage']:
        cover_images = self._cover_image_full
        if len(cover_images) == 1:
            return next(iter(self)).cover_image_obj
        elif cover_images:
            popup_ok(f'Warning: found {len(cover_images)} cover images for {self.album_dir}')
        return None

    def get_album_data_rows(self, editable: bool = False):
        rows = []
        skip = {'tracks'}
        always_ro = {'mp4'}
        ele_binds = {}
        for key, value in self.album_info.to_dict().items():
            if key in skip:
                continue
            disabled = not editable or key in always_ro

            key_ele, val_key = label_and_val_key('album', key)
            if key == 'type':
                types = [de.real_name for de in DiscoEntryType]
                if value and value not in types:
                    types.append(value)
                val_ele = Combo(types, value, key=val_key, disabled=disabled)
            else:
                val_ele, bind = value_ele(value, val_key, disabled)
                if bind:
                    ele_binds[val_key] = bind

            rows.append([key_ele, val_ele])

        return (resize_text_column(rows) if rows else rows), ele_binds

    def get_cover_image_diff(self, new_album_info: AlbumInfo) -> Optional[tuple[Image, Image, PILImage, bytes]]:
        if new_album_info.cover_path:
            src_pil_image = self.cover_image_full_obj
            new_pil_image, img_data = new_album_info.get_new_cover(self.album_dir, src_pil_image, force=True)
            if new_pil_image is not None:
                src_img_ele = self.cover_image_thumbnail('img::album::cover-src', False)
                new_img_ele = self._make_thumnail_image(new_pil_image, 'img::album::cover-new')
                return src_img_ele, new_img_ele, new_pil_image, img_data
        return None

    def get_album_diff_rows(self, new_album_info: AlbumInfo, title_case: bool = False, add_genre: bool = False):
        rows = []
        skip = {'tracks'}
        ele_binds = {}
        new_info_dict = new_album_info.to_dict(title_case)
        for key, src_val in self._src_album_info.to_dict(title_case).items():
            if key in skip:
                continue

            new_val = new_info_dict[key]
            if key == 'genre' and add_genre:
                new_vals = {new_val} if isinstance(new_val, str) else set(new_val)
                new_vals.update(src_val)
                new_val = sorted(new_vals)

            if (src_val or new_val) and src_val != new_val:
                self.log.debug(f'album: {key} is different: {src_val=!r} != {new_val=!r}')
                label, sep_1, sep_2, src_key, new_key = label_and_diff_keys('album', key)
                src_ele, src_bind = value_ele(src_val, src_key, True, 45)
                new_ele, new_bind = value_ele(new_val, new_key, True, 45)
                rows.append([label, sep_1, src_ele, sep_2, new_ele])
                if src_bind:
                    ele_binds[src_key] = src_bind
                if new_bind:
                    ele_binds[new_key] = new_bind

        return (resize_text_column(rows) if rows else rows), ele_binds

    def get_dest_path(self, new_album_info: AlbumInfo, dest_base_dir: Path) -> Optional[Path]:
        try:
            expected_rel_dir = new_album_info.expected_rel_dir
        except AttributeError:
            return None
        dest_base_dir = new_album_info.dest_base_dir(self.album_dir, dest_base_dir)
        return dest_base_dir.joinpath(expected_rel_dir)


def value_ele(
    value: Any, val_key: str, disabled: bool, list_width: int = 30, no_add: bool = False
) -> tuple[Element, Optional[dict[str, 'Event']]]:
    bind = None
    if isinstance(value, bool):
        val_ele = Checkbox('', default=value, key=val_key, disabled=disabled, pad=(0, 0))
    elif isinstance(value, list):
        val_ele = Listbox(
            value,
            default_values=value,
            key=val_key,
            disabled=disabled,
            size=(list_width, len(value)),
            no_scrollbar=True,
            select_mode='extended',  # extended, browse, single, multiple
        )
        if not no_add and val_key.startswith('val::'):
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
        if value and str(value).startswith(('http://', 'https://')):
            val_ele = Input(value, key=val_key, disabled=disabled, tooltip='Open with ctrl + click')
            bind = {'<Control-Button-1>': ':::open_link'}
        else:
            val_ele = Input(value, key=val_key, disabled=disabled)

    return val_ele, bind


def make_thumbnail(pil_img: PILImage, size: tuple[int, int]) -> bytes:
    image = pil_img.copy()
    image.thumbnail(size)
    bio = BytesIO()
    image.save(bio, format='PNG')
    return bio.getvalue()


class TrackBlock:
    def __init__(
        self, album_block: AlbumBlock, track: SongFile, info: TrackInfo, cover_size: tuple[int, int] = (250, 250)
    ):
        self.album_block = album_block
        self.track = track
        self.cover_size = cover_size
        self._src_info = info
        self._new_info = None

    @property
    def log(self):
        return self.album_block.view.log

    @property
    def info(self):
        if self._new_info is None:
            return self._src_info
        return self._new_info

    @info.setter
    def info(self, value: TrackInfo):
        self._new_info = value

    @cached_property
    def cover_image_obj(self) -> Optional['PILImage']:
        try:
            return self.track.get_cover_image()
        except Exception:
            self.log.error(f'Unable to load cover image for {self.track}')
            return None

    @cached_property
    def _cover_image_full(self) -> Optional[bytes]:
        if (image := self.cover_image_obj) is not None:
            bio = BytesIO()
            image.save(bio, format='PNG')
            return bio.getvalue()
        return None

    @cached_property
    def _cover_image_thumbnail(self) -> Optional[bytes]:
        if (image := self.cover_image_obj) is not None:
            return make_thumbnail(image, self.cover_size)
        return None

    @property
    def cover_image_thumbnail(self) -> Image:
        # If self._cover_image_thumbnail is None, it will be a blank frame
        return Image(
            data=self._cover_image_thumbnail, size=self.cover_size, key=f'img::{self.path_str}::cover-thumb',
            enable_events=True
        )

    @property
    def cover_image(self) -> Image:
        size = self.cover_image_obj.size if self.cover_image_obj is not None else (100, 100)
        return Image(data=self._cover_image_full, size=size, key=f'img::{self.path_str}::cover-full')

    @cached_property
    def tag_values(self) -> dict[str, tuple[str, Any]]:
        tag_name_map = typed_tag_name_map.get(self.track.tag_type, {})
        tag_values = {}
        flac = self.track.tag_type == 'flac'
        for tag, val in sorted(self.track.tags.items()):
            if flac:
                tag_name = tag_name_map.get(tag, tag)
            else:
                tag_name = tag_name_map.get(tag[:4], tag)

            if tag_name == 'Album Cover':
                continue

            tag_values[tag] = (tag_name, val)
        return tag_values

    @cached_property
    def path_str(self) -> str:
        return self.track.path.as_posix()

    @cached_property
    def file_name(self) -> str:
        return self.track.path.name

    def get_tag_rows(self, editable: bool = True) -> tuple[Layout, EleBinds]:
        rows = []
        ele_binds = {}
        flac = self.track.tag_type == 'flac'
        for tag, (tag_name, val) in self.tag_values.items():
            self.log.info(f'Processing {self.path_str} {tag=!r} {tag_name=!r} {val=!r}')
            key_ele = Text(tag_name, key=f'tag::{self.path_str}::{tag}')
            val_key = f'val::{self.path_str}::{tag}'
            if tag_name == 'Lyrics':
                if isinstance(val, list):
                    val = val[0]
                val_ele = Multiline(val, size=(45, 4), key=val_key, disabled=True)
            else:
                if flac and tag_name != 'genre':
                    val = val[0]
                val_ele, bind = value_ele(val, val_key, True, no_add=True, list_width=45)
                bind = bind or {}
                bind['<Button-1>'] = ':::row_clicked'
                bind['<Shift-Button-1>'] = ':::tag_clicked'
                ele_binds[val_key] = bind

            sel_box = Checkbox('', key=f'del::{self.path_str}::{tag}', visible=editable, enable_events=True)
            rows.append([key_ele, sel_box, val_ele])

        return (resize_text_column(rows) if rows else rows), ele_binds

    def get_info_rows(self, editable: bool = True):
        rows = []
        for key, value in self.info.to_dict().items():
            key_ele, val_key = label_and_val_key(self.path_str, key)
            val_ele, bind = value_ele(value, val_key, not editable)
            rows.append([key_ele, val_ele])

        return resize_text_column(rows) if rows else rows

    def get_diff_rows(self, new_track_info: TrackInfo, title_case: bool = False, add_genre: bool = False):
        album_src_genres = set(self.album_block._src_album_info.norm_genres())
        album_new_genres = set(new_track_info.album.norm_genres())
        if add_genre:
            album_new_genres.update(album_src_genres)

        rows = []
        new_info_dict = new_track_info.to_dict(title_case)
        for key, src_val in self._src_info.to_dict(title_case).items():
            new_val = new_info_dict[key]
            skip = False
            if key == 'genre':
                # TODO: OST/Ost shows up here
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
                src_ele, src_bind = value_ele(src_val, src_key, True)
                new_ele, new_bind = value_ele(new_val, new_key, True)
                rows.append([label, sep_1, src_ele, sep_2, new_ele])

        return resize_text_column(rows) if rows else rows

    def get_basic_info_row(self):
        track = self.track
        return [
            Text('File:'),
            Input(track.path.name, size=(50, 1), disabled=True),
            VerticalSeparator(),
            Text('Length:'),
            Input(track.length_str, size=(6, 1), disabled=True),
            VerticalSeparator(),
            Text('Type:'),
            Input(track.tag_version, size=(10, 1), disabled=True),
        ]

    def as_info_rows(self, editable: bool = True):
        yield [HorizontalSeparator()]
        yield self.get_basic_info_row()
        yield [Column(self.get_info_rows(editable), key=f'col::{self.path_str}::tags')]

    def as_all_tag_rows(self, editable: bool = True):
        cover = Column([[self.cover_image_thumbnail]], key=f'col::{self.path_str}::cover')
        tag_rows, ele_binds = self.get_tag_rows(editable)
        tags = Column(tag_rows, key=f'col::{self.path_str}::tags')
        layout = [[HorizontalSeparator()], self.get_basic_info_row(), [cover, tags]]
        return layout, ele_binds

    def as_diff_rows(self, new_track_info: TrackInfo, title_case: bool = False, add_genre: bool = False):
        yield [HorizontalSeparator()]
        new_name = new_track_info.expected_name(self.track)
        if self.track.path.name != new_name:
            yield get_a_to_b('File Rename:', self.track.path.name, new_name, self.path_str, 'file_name')
        else:
            yield [
                Text('File:'),
                Input(self.track.path.name, disabled=True, key=f'src::{self.path_str}::file_name'),
                Text('(no change)'),
            ]

        if diff_rows := self.get_diff_rows(new_track_info, title_case, add_genre):
            yield [Column(diff_rows, key=f'col::{self.path_str}::diff')]
        else:
            yield []
