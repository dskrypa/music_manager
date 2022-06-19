"""
High level PySimpleGUI elements that represent Plex objects

:author: Doug Skrypa
"""

from __future__ import annotations

import logging
from datetime import datetime
from functools import cached_property
from itertools import count
from math import ceil
from operator import itemgetter
from pathlib import Path
from tempfile import gettempdir
from typing import TYPE_CHECKING, Union, Collection, Optional, Iterable
from urllib.parse import quote

from cachetools import LRUCache
from plexapi.audio import Track, Album, Artist
from plexapi.video import Movie, Show, Season, Episode
from PySimpleGUI import Column, HorizontalSeparator, Image, Button
from requests import RequestException

from ds_tools.images.utils import ImageType, as_image, scale_image
from ...common.ratings import stars
from ..icons import Icons
from ..elements import ExtendedImage, Rating, ExtText
from ..popups.text import popup_ok
from ..progress import Spinner

if TYPE_CHECKING:
    from PIL.Image import Image as PILImage
    from requests import Response

__all__ = ['ResultRow', 'ResultTable']
log = logging.getLogger(__name__)

PlexObj = Union[Track, Album, Artist, Movie, Show, Season, Episode]
ImageOrImages = Union[ImageType, tuple[ImageType, ImageType]]

JPEG_RAW_MODES = {'1', 'L', 'RGB', 'RGBX', 'CMYK', 'YCbCr'}
FIELD_SIZES = {
    'year': (4, 1),
    'artist': (30, 1),
    'album': (30, 1),
    'show': (30, 1),
    'season': (20, 1),
    'title': (30, 1),
    'duration': (6, 1),
    'plays': (5, 1),
}
TYPE_FIELDS_MAP = {
    'track': {'cover', 'year', 'artist', 'album', 'title', 'duration', 'plays', 'rating', 'play'},
    'album': {'cover', 'year', 'artist', 'title', 'plays', 'rating'},
    'artist': {'image', 'title'},
    'movie': {'image', 'year', 'title', 'duration', 'plays', 'rating', 'play'},
    'show': {'image', 'year', 'title', 'duration', 'plays', 'rating'},
    'season': {'image', 'show', 'title', 'plays'},
    'episode': {'image', 'year', 'show', 'season', 'title', 'duration', 'plays', 'rating', 'play'},
}
DEFAULT_SORT_FIELDS = {
    'track': ('artist', 'album', 'title'),
    'album': ('artist', 'year', 'title'),
    'artist': ('title',),
    'movie': ('title', 'year'),
    'show': ('title', 'year'),
    'season': ('show', 'title'),
    'episode': ('show', 'season', 'title'),
}


class ImageCache:
    def __init__(self, cache_dir: Union[str, Path] = None, size: int = 100):
        self.icons_dir = Path(__file__).resolve().parents[4].joinpath('icons')
        if cache_dir is None:
            self.cache_dir = Path(gettempdir()).joinpath('plex', 'images')
        else:
            self.cache_dir = Path(cache_dir).expanduser()
        self.mem_cache = LRUCache(size)

    def get_images(self, plex_obj: PlexObj, img_size: tuple[int, int]) -> ImageOrImages:
        full_rel_path: str = plex_obj.thumb[1:]
        cache_key = (full_rel_path, img_size)
        try:
            return self.mem_cache[cache_key]
        except KeyError:
            pass

        self.mem_cache[cache_key] = images = self._get_images(plex_obj, full_rel_path, img_size)
        return images

    def _get_images(self, plex_obj: PlexObj, full_rel_path: str, img_size: tuple[int, int]) -> ImageOrImages:
        full_size_path = self.cache_dir.joinpath(full_rel_path)
        thumb_path = full_size_path.with_name('{}__{}x{}'.format(full_size_path.name, *img_size))
        if self._can_use_thumb_path(thumb_path):
            return thumb_path, full_size_path
        elif full_size_path.exists():
            return convert_and_save_thumbnail(full_size_path, thumb_path, img_size), full_size_path

        server = plex_obj._server
        try:
            resp: Response = server._session.get(server.url(plex_obj.thumb), headers=server._headers())
            resp.raise_for_status()
        except RequestException as e:
            log.debug(f'Error retrieving image for {plex_obj}: {e}')
            return self.icons_dir.joinpath('x.png')
        else:
            log.debug(f'Saving image for {plex_obj} to {full_size_path.as_posix()}')
            save_image(resp.content, full_size_path)
            return convert_and_save_thumbnail(resp.content, thumb_path, img_size), full_size_path

    @classmethod
    def _can_use_thumb_path(cls, path: Path) -> bool:
        if not path.exists():
            return False
        if path.stat().st_size == 0:
            path.unlink()
            return False
        return True


class Result:
    def __init__(self, plex_obj: PlexObj):
        self.plex_obj = plex_obj
        self.type = plex_obj.TYPE
        self.fields = TYPE_FIELDS_MAP[self.type]

    def __getitem__(self, key: str):
        return self.field_value_map[key]

    def get(self, key: str, default=None):
        return self.field_value_map.get(key, default)

    def get_link(self, key: str, default: str = None) -> Optional[str]:
        return self.plex_links.get(key, default)

    @property
    def duration(self) -> str:
        # Invalid for Season & Album
        duration = int(self.plex_obj.duration / 1000)
        duration_dt = datetime.fromtimestamp(duration)
        return duration_dt.strftime('%M:%S' if duration < 3600 else '%H:%M:%S')

    @cached_property
    def field_value_map(self) -> dict[str, str]:
        plex_obj = self.plex_obj
        field_value_map = {'title': plex_obj.title}
        if isinstance(plex_obj, Artist):
            return field_value_map

        field_value_map['plays'] = plex_obj.viewCount
        if not isinstance(plex_obj, (Season, Album)):
            field_value_map['duration'] = self.duration
        if not isinstance(plex_obj, (Track, Season)):
            field_value_map['year'] = plex_obj.year

        if isinstance(plex_obj, Track):
            field_value_map.update(
                artist=plex_obj.grandparentTitle,
                album=plex_obj.parentTitle,
                year=plex_obj._data.attrib.get('parentYear'),
            )
        elif isinstance(plex_obj, Album):
            field_value_map['artist'] = plex_obj.parentTitle
        elif isinstance(plex_obj, Season):
            field_value_map['show'] = plex_obj.parentTitle
        elif isinstance(plex_obj, Episode):
            field_value_map.update(show=plex_obj.grandparentTitle, season=plex_obj.parentTitle)

        return field_value_map

    @property
    def rating(self) -> Optional[int]:
        return self.plex_obj.userRating if not isinstance(self.plex_obj, Season) else None

    def set_rating(self, rating: int):
        log.info(f'Updating rating for {self.plex_obj} to {stars(rating)}')
        self.plex_obj.edit(**{'userRating.value': rating})

    @cached_property
    def plex_links(self) -> dict[str, str]:
        plex_obj = self.plex_obj
        srv = plex_obj._server
        base = f'{srv._baseurl}/web/index.html#!/server/{srv.machineIdentifier}/details?library%3Acontent.library&key='
        if isinstance(plex_obj, Track):
            return {'artist': f'{base}{quote(plex_obj.grandparentKey)}', 'album': f'{base}{quote(plex_obj.parentKey)}'}
        elif isinstance(plex_obj, Album):
            return {'artist': f'{base}{quote(plex_obj.parentKey)}', 'title': f'{base}{quote(plex_obj.key)}'}
        elif isinstance(plex_obj, (Artist, Movie, Show)):
            return {'title': f'{base}{quote(plex_obj.key)}'}
        elif isinstance(plex_obj, Season):
            return {'show': f'{base}{quote(plex_obj.parentKey)}', 'title': f'{base}{quote(plex_obj.key)}'}
        elif isinstance(plex_obj, Episode):
            return {
                'show': f'{base}{quote(plex_obj.grandparentKey)}',
                'season': f'{base}{quote(plex_obj.parentKey)}',
                'title': f'{base}{quote(plex_obj.key)}',
            }
        else:
            return {}


class ResultRow:
    __counter = count()
    _img_cache = ImageCache()
    _play_icon = Icons(15).draw_base64('play')

    def __init__(self, img_size: tuple[int, int] = None):
        self.img_size = img_size or (40, 40)
        self._num = next(self.__counter)
        kp = f'result:{self._num}'
        self.image = ExtendedImage(size=self.img_size, key=f'{kp}:cover', pad=((20, 5), 3))
        self.play_button = Button(image_data=self._play_icon, key=f'{kp}:play')
        self.result_type = None
        self.fields: dict[str, ExtText] = {
            field: ExtText(
                size=size, key=f'{kp}:{field}', justification='right' if field in ('duration', 'plays') else None
            )
            for field, size in FIELD_SIZES.items() if field != 'play'
        }
        self.rating = Rating(key=f'{kp}:rating', change_cb=self.rating_changed)
        self.visible = True
        self.row = [self.image, *(cell.pin for cell in self.fields.values()), self.rating, self.play_button]
        self.result: Optional[Result] = None

    def hide(self):
        self.visible = False
        self.row[0].hide_row()

    def clear(self, hide: bool = True):
        # TODO: Subsequent queries sometimes still show old values, specifically year, at least
        if hide:
            self.hide()
        for text_ele in self.fields.values():
            text_ele.value = ''
        self.image.image = None
        self.image._current_size = self.img_size  # Reset size in case the previous image was smaller
        self.rating.update(0)

    def set_result_type(self, result_type: str, show_fields: Collection = None, hide: bool = False):
        if result_type != self.result_type:
            self.result_type = result_type
            show_fields = show_fields or TYPE_FIELDS_MAP[result_type]
            for field, text_ele in self.fields.items():
                text_ele.update_visibility(field in show_fields)
            self.play_button.update(visible='play' in show_fields)
            if hide:
                self.hide()

    def update(self, result: Result):
        self.result = result
        self.fields['title'].update(result.plex_obj.title, link=result.get_link('title'))
        for field, value in result.field_value_map.items():
            self.fields[field].update(value, link=result.get_link(field))
        if (rating := result.rating) is not None:
            self.rating.update(rating)
        self.image.image = self._img_cache.get_images(result.plex_obj, self.img_size)
        self.row[0].unhide_row()
        self.visible = True

    def rating_changed(self, rating: Rating):
        self.result.set_rating(rating.rating)


class ResultTable(Column):
    _default_params = {
        'scrollable': True, 'vertical_scroll_only': True, 'element_justification': 'center', 'justification': 'center'
    }
    __counter = count()

    def __init__(self, rows: int = 50, img_size: tuple[int, int] = None, sort_by: Iterable[str] = None, **kwargs):
        self.img_size = img_size
        self.rows = [ResultRow(img_size) for _ in range(rows)]
        header_sizes = {'cover': (4, 1), 'image': (4, 1), **FIELD_SIZES, 'rating': (5, 1), 'play': (4, 1)}
        self.headers: dict[str, ExtText] = {
            header.strip(): ExtText(
                header.title(),
                size=size,
                key=f'header:{header}',
                justification='right' if header in ('duration', 'plays', 'play') else None,
            )
            for header, size in header_sizes.items()
        }
        self.header_column = Column([[h.pin for h in self.headers.values()]], key='headers', pad=(0, 0))
        self.result_type = None
        self.results: Optional[list[Result]] = None
        self.result_count = 0
        self.last_page_count = 0
        self.sort_by = sort_by or ('title',)
        self._num = next(self.__counter)
        kwargs.setdefault('key', f'result_table:{self._num}')
        for key, val in self._default_params.items():
            kwargs.setdefault(key, val)
        layout = [
            [Image(size=(kwargs['size'][0], 1), pad=(0, 0))],
            [self.header_column],
            [HorizontalSeparator()],
            *(tr.row for tr in self.rows),
        ]
        super().__init__(layout, **kwargs)

    def __getitem__(self, row: int) -> ResultRow:
        return self.rows[row]

    def set_result_type(self, result_type: str):
        if result_type != self.result_type:
            self.result_type = result_type
            self.sort_by = DEFAULT_SORT_FIELDS[result_type]
            show_fields = TYPE_FIELDS_MAP[result_type]
            for field, header_ele in self.headers.items():
                header_ele.update_visibility(field in show_fields)
            for row in self.rows:
                if hide := row.visible:
                    row.clear(False)
                row.set_result_type(result_type, show_fields, hide)
            self.expand(expand_x=True, expand_row=True)
            self.contents_changed()

    def show_results(self, results: set[PlexObj]):
        self.results = results = sorted(map(Result, results), key=itemgetter(*self.sort_by))
        self.result_count = result_count = len(results)
        pages = ceil(result_count / 100)
        log.info(f'Found {result_count} ({pages=}) {self.result_type}s')
        self.show_page(1)

    def show_page(self, page: int):
        per_page = len(self.rows)
        pages = ceil(self.result_count / per_page)
        if pages < page or page <= 0:
            return popup_ok(f'Invalid {page=} - must be a value between 1 and {pages}')

        start = per_page * (page - 1)
        end = start + per_page if page < pages else self.result_count
        self.last_page_count = total = end - start
        log.debug(f'Showing {page=} with {total}/{self.result_count} results ({start} - {end})')
        for row, obj in zip(self.rows, self.results[start:end]):
            row.update(obj)

        if total < per_page:
            for i in range(total, per_page):
                self.rows[i].clear()

        try:
            self.TKColFrame.canvas.yview_moveto(0)  # noqa
        except Exception:
            pass
        # self.expand(expand_y=True)  # including expand_x=True in this call results in no vertical scroll
        # self.expand(expand_x=True, expand_row=True)  # results in shorter y, but scroll works...
        self.expand(True, True)  # The behavior referenced by the above comment has now reversed.
        self.contents_changed()

    def sort_results(self, sort_by: str):
        # TODO: Add handling for clicking a column header to sort ascending/descending by that column
        #  + remember last field+asc/desc per obj type
        self.sort_by = sort_by
        with Spinner():
            self.results = sorted(self.results, key=itemgetter(*self.sort_by))
            self.show_page(1)

    def clear_results(self):
        self.results = None
        self.result_count = 0
        if self.last_page_count:
            with Spinner():
                for i in range(self.last_page_count):
                    self.rows[i].clear()

        self.last_page_count = 0


def save_image(image: Union[PILImage, bytes], path: Path) -> Union[PILImage, bytes]:
    if not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)

    if isinstance(image, bytes):
        path.write_bytes(image)
    else:
        save_fmt = 'png' if image.mode == 'RGBA' else 'jpeg'
        if save_fmt == 'jpeg' and image.mode not in JPEG_RAW_MODES:
            image = image.convert('RGB')
        with path.open('wb') as f:
            image.save(f, save_fmt)

    return image


def convert_and_save_thumbnail(image: ImageType, thumb_path: Path, img_size: tuple[int, int]):
    thumbnail = scale_image(as_image(image), *img_size)
    log.debug(f'Saving image thumbnail to {thumb_path.as_posix()}')
    return save_image(thumbnail, thumb_path)
