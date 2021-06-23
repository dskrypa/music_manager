"""
High level PySimpleGUI elements that represent Plex objects

:author: Doug Skrypa
"""

import logging
from base64 import b64encode
from datetime import datetime
from functools import cached_property
from io import BytesIO
from itertools import count
from math import ceil
from operator import itemgetter
from pathlib import Path
from tempfile import gettempdir
from typing import Union, Collection, Optional, Iterable
from urllib.parse import quote

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

__all__ = ['ResultRow', 'ResultTable']
log = logging.getLogger(__name__)
ICONS_DIR = Path(__file__).resolve().parents[4].joinpath('icons')
TMP_DIR = Path(gettempdir()).joinpath('plex', 'images')
PlexObj = Union[Track, Album, Artist, Movie, Show, Season, Episode]
PLAY_ICON = Icons(15).draw('play')
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

    def get_images(self, img_size: tuple[int, int]) -> Union[ImageType, tuple[ImageType, ImageType]]:
        full_size_path = TMP_DIR.joinpath(self.plex_obj.thumb[1:])
        thumb_path = full_size_path.with_name('{}__{}x{}'.format(full_size_path.name, *img_size))
        if thumb_path.exists():
            return thumb_path, full_size_path
        elif full_size_path.exists():
            return convert_and_save_thumbnail(full_size_path, thumb_path, img_size), full_size_path

        server = self.plex_obj._server
        try:
            resp = server._session.get(server.url(self.plex_obj.thumb), headers=server._headers())
        except RequestException as e:
            log.debug(f'Error retrieving image for {self.plex_obj}: {e}')
            return ICONS_DIR.joinpath('x.png')
        else:
            if not full_size_path.parent.exists():
                full_size_path.parent.mkdir(parents=True)
            log.debug(f'Saving image for {self.plex_obj} to {full_size_path.as_posix()}')
            image_bytes = resp.content
            with full_size_path.open('wb') as f:
                f.write(image_bytes)
            return convert_and_save_thumbnail(image_bytes, thumb_path, img_size), full_size_path

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
    _play_icon = None

    def __init__(self, img_size: tuple[int, int] = None):
        self.img_size = img_size or (40, 40)
        self._num = next(self.__counter)
        kp = f'result:{self._num}'
        self.image = ExtendedImage(size=self.img_size, key=f'{kp}:cover', pad=((20, 5), 3))
        if self._play_icon is None:
            ResultRow._play_icon = img_to_b64(PLAY_ICON)
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
        self.image.image = result.get_images(self.img_size)
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


def convert_and_save_thumbnail(image: ImageType, thumb_path: Path, img_size: tuple[int, int]):
    thumbnail = scale_image(as_image(image), *img_size)
    if not thumb_path.parent.exists():
        thumb_path.parent.mkdir(parents=True)
    log.debug(f'Saving image thumbnail to {thumb_path.as_posix()}')
    with thumb_path.open('wb') as f:
        thumbnail.save(f, 'png' if thumbnail.mode == 'RGBA' else 'jpeg')
    return thumbnail


def img_to_b64(image) -> bytes:
    bio = BytesIO()
    image.save(bio, 'PNG')
    return b64encode(bio.getvalue())
