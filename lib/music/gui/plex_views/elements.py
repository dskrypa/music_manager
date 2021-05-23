"""
High level PySimpleGUI elements that represent Plex objects

:author: Doug Skrypa
"""

import logging
from datetime import datetime
from itertools import count
from math import ceil
from operator import attrgetter
from pathlib import Path
from tempfile import gettempdir
from typing import Union, Collection, Optional
from urllib.parse import quote

from plexapi.base import PlexPartialObject
from plexapi.audio import Track, Album, Artist
from plexapi.video import Movie, Show, Season, Episode
from PySimpleGUI import Column, HorizontalSeparator, Image
from requests import RequestException

from ...common.ratings import stars
from ...common.images import as_image, scale_image, ImageType
from ..constants import LoadingSpinner
from ..elements import ExtendedImage, Rating, ExtText
from ..popups.text import popup_ok
from ..progress import Spinner

__all__ = ['ResultRow', 'ResultTable']
log = logging.getLogger(__name__)
ICONS_DIR = Path(__file__).resolve().parents[4].joinpath('icons')
TMP_DIR = Path(gettempdir()).joinpath('plex', 'images')
Result = Union[Track, Album, Artist, Movie, Show, Season, Episode]

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
    'track': {'cover', 'year', 'artist', 'album', 'title', 'duration', 'plays', 'rating'},
    'album': {'cover', 'year', 'artist', 'title', 'plays', 'rating'},
    'artist': {'image', 'title'},
    'movie': {'image', 'year', 'title', 'duration', 'plays', 'rating'},
    'show': {'image', 'year', 'title', 'duration', 'plays', 'rating'},
    'season': {'image', 'show', 'title', 'plays'},
    'episode': {'image', 'year', 'show', 'season', 'title', 'duration', 'plays', 'rating'},
}


class ResultRow:
    __counter = count()

    def __init__(self, img_size: tuple[int, int] = None):
        self.img_size = img_size or (40, 40)
        self._num = next(self.__counter)
        kp = f'result:{self._num}'
        self.image = ExtendedImage(size=self.img_size, key=f'{kp}:cover', pad=((20, 5), 3))
        self.result_type = None
        self.fields: dict[str, ExtText] = {
            field: ExtText(
                size=size, key=f'{kp}:{field}', justification='right' if field in ('duration', 'plays') else None
            )
            for field, size in FIELD_SIZES.items()
        }
        self.rating = Rating(key=f'{kp}:rating', change_cb=self.rating_changed)
        row = [self.image, *(cell.pin for cell in self.fields.values()), self.rating]
        self.column = Column(
            [row], key=kp, visible=False, justification='center', element_justification='center', expand_x=True
        )
        self.plex_obj: Optional[PlexPartialObject] = None

    def hide(self):
        self.column.update(visible=False)

    def clear(self, hide: bool = True):
        if hide:
            self.hide()
        for text_ele in self.fields.values():
            text_ele.value = ''
        self.image.image = None
        self.rating.update(0)

    def set_result_type(self, result_type: str, show_fields: Collection = None, hide: bool = False):
        if result_type != self.result_type:
            self.result_type = result_type
            show_fields = show_fields or TYPE_FIELDS_MAP[result_type]
            for field, text_ele in self.fields.items():
                text_ele.update_visibility(field in show_fields)
            if hide:
                self.hide()

    def update(self, result: Result):
        self.plex_obj = result
        field_link_map = plex_links(result)
        field_value_map = field_values(result)
        self.fields['title'].update(result.title, link=field_link_map.get('title'))
        for field, value in field_value_map.items():
            self.fields[field].update(value, link=field_link_map.get(field))
        if not isinstance(result, Season):
            self.rating.update(result.userRating)
        self.image.image = get_images(result, self.img_size)
        self.column.update(visible=True)
        self.column.expand(True, True, True)

    def rating_changed(self, rating: Rating):
        log.info(f'Updating rating for {self.plex_obj} to {stars(rating.rating)}')
        self.plex_obj.edit(**{'userRating.value': rating.rating})


class ResultTable(Column):
    __counter = count()

    def __init__(self, rows: int = 100, img_size: tuple[int, int] = None, sort_by: str = None, **kwargs):
        self.rows = [ResultRow(img_size) for _ in range(rows)]
        header_sizes = {'cover': (4, 1), 'image': (4, 1), **FIELD_SIZES, 'rating': (5, 1)}
        self.headers: dict[str, ExtText] = {
            header: ExtText(
                header.title(),
                size=size,
                key=f'header:{header}',
                justification='right' if header in ('duration', 'plays') else None,
            )
            for header, size in header_sizes.items()
        }
        self.header_column = Column([[h.pin for h in self.headers.values()]], key='headers', pad=(0, 0))
        self.result_type = None
        self.results: Optional[list[Result]] = None
        self.result_count = 0
        self.last_page_count = 0
        self.sort_by = sort_by or 'title'
        self._num = next(self.__counter)
        kwargs.setdefault('key', f'result_table:{self._num}')
        kwargs.setdefault('scrollable', True)
        kwargs.setdefault('vertical_scroll_only', True)
        kwargs.setdefault('element_justification', 'center')
        kwargs.setdefault('justification', 'center')
        layout = [
            [self.header_column],
            [HorizontalSeparator()],
            *([tr.column] for tr in self.rows),
            [Image(size=(kwargs['size'][0], 1), pad=(0, 0))]
        ]
        super().__init__(layout, **kwargs)

    def set_result_type(self, result_type: str):
        if result_type != self.result_type:
            self.result_type = result_type
            show_fields = TYPE_FIELDS_MAP[result_type]
            for field, header_ele in self.headers.items():
                header_ele.update_visibility(field in show_fields)
            for row in self.rows:
                if hide := row.column._visible:
                    row.clear(False)
                row.set_result_type(result_type, show_fields, hide)
            self.expand(expand_x=True, expand_row=True)
            self.contents_changed()

    def show_results(self, results: set[Result], spinner: Spinner):
        self.results = results = sorted(results, key=attrgetter(self.sort_by))
        self.result_count = result_count = len(results)
        pages = ceil(result_count / 100)
        log.info(f'Found {result_count} ({pages=}) {self.result_type}s')
        self.show_page(1, spinner)

    def show_page(self, page: int, spinner: Spinner):
        per_page = len(self.rows)
        pages = ceil(self.result_count / per_page)
        if pages < page or page <= 0:
            return popup_ok(f'Invalid {page=} - must be a value between 1 and {pages}')

        start = per_page * (page - 1)
        end = start + per_page if page < pages else self.result_count
        self.last_page_count = total = end - start
        log.debug(f'Showing {page=} with {total}/{self.result_count} results ({start} - {end})')
        for row, obj in spinner(zip(self.rows, self.results[start:end])):
            row.update(obj)

        if total < per_page:
            for i in spinner(range(total, per_page)):
                self.rows[i].clear()

        try:
            self.TKColFrame.canvas.yview_moveto(0)  # noqa
        except Exception:
            pass
        self.expand(expand_y=True)  # including expand_x=True in this call results in no vertical scroll
        self.expand(expand_x=True, expand_row=True)  # results in shorter y, but scroll works...
        self.contents_changed()

    def sort_results(self, sort_by: str):
        self.sort_by = sort_by
        with Spinner(LoadingSpinner.blue_dots) as spinner:
            self.results = sorted(self.results, key=attrgetter(self.sort_by))
            self.show_page(1, spinner)

    def clear_results(self):
        self.results = None
        self.result_count = 0
        if self.last_page_count:
            with Spinner(LoadingSpinner.blue_dots) as spinner:
                for i in spinner(range(self.last_page_count)):
                    self.rows[i].clear()

        self.last_page_count = 0


def get_images(result: Result, img_size: tuple[int, int]) -> Union[ImageType, tuple[ImageType, ImageType]]:
    full_size_path = TMP_DIR.joinpath(result.thumb[1:])
    thumb_path = full_size_path.with_name('{}__{}x{}'.format(full_size_path.name, *img_size))
    if thumb_path.exists():
        return thumb_path, full_size_path
    elif full_size_path.exists():
        return convert_and_save_thumbnail(full_size_path, thumb_path, img_size), full_size_path

    server = result._server
    try:
        resp = server._session.get(server.url(result.thumb), headers=server._headers())
    except RequestException as e:
        log.debug(f'Error retrieving image for {result}: {e}')
        return ICONS_DIR.joinpath('x.png')
    else:
        if not full_size_path.parent.exists():
            full_size_path.parent.mkdir(parents=True)
        log.debug(f'Saving image for {result} to {full_size_path.as_posix()}')
        image_bytes = resp.content
        with full_size_path.open('wb') as f:
            f.write(image_bytes)
        return convert_and_save_thumbnail(image_bytes, thumb_path, img_size), full_size_path


def convert_and_save_thumbnail(image: ImageType, thumb_path: Path, img_size: tuple[int, int]):
    thumbnail = scale_image(as_image(image), *img_size)
    if not thumb_path.parent.exists():
        thumb_path.parent.mkdir(parents=True)
    log.debug(f'Saving image thumbnail to {thumb_path.as_posix()}')
    with thumb_path.open('wb') as f:
        thumbnail.save(f, 'png' if thumbnail.mode == 'RGBA' else 'jpeg')
    return thumbnail


def format_duration(duration_ms: int) -> str:
    duration = int(duration_ms / 1000)
    duration_dt = datetime.fromtimestamp(duration)
    return duration_dt.strftime('%M:%S' if duration < 3600 else '%H:%M:%S')


def field_values(result: Result) -> dict[str, str]:
    if isinstance(result, Artist):
        return {}

    field_value_map = {'plays': result.viewCount}
    if not isinstance(result, (Season, Album)):
        field_value_map['duration'] = format_duration(result.duration)
    if not isinstance(result, (Track, Season)):
        field_value_map['year'] = result.year

    if isinstance(result, Track):
        field_value_map.update(
            artist=result.grandparentTitle, album=result.parentTitle, year=result._data.attrib.get('parentYear')
        )
    elif isinstance(result, Album):
        field_value_map['artist'] = result.parentTitle
    elif isinstance(result, Season):
        field_value_map['show'] = result.parentTitle
    elif isinstance(result, Episode):
        field_value_map.update(show=result.grandparentTitle, season=result.parentTitle)

    return field_value_map


def plex_links(result: Result) -> dict[str, str]:
    srv = result._server
    base = f'{srv._baseurl}/web/index.html#!/server/{srv.machineIdentifier}/details?library%3Acontent.library&key='
    if isinstance(result, Track):
        return {'artist': f'{base}{quote(result.grandparentKey)}', 'album': f'{base}{quote(result.parentKey)}'}
    elif isinstance(result, Album):
        return {'artist': f'{base}{quote(result.parentKey)}', 'title': f'{base}{quote(result.key)}'}
    elif isinstance(result, (Artist, Movie, Show)):
        return {'title': f'{base}{quote(result.key)}'}
    elif isinstance(result, Season):
        return {'show': f'{base}{quote(result.parentKey)}', 'title': f'{base}{quote(result.key)}'}
    elif isinstance(result, Episode):
        return {
            'show': f'{base}{quote(result.grandparentKey)}',
            'season': f'{base}{quote(result.parentKey)}',
            'title': f'{base}{quote(result.key)}',
        }
    else:
        return {}
