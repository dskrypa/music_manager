"""
Classes representing tracks and albums, with methods to load from file or save to file, and to update/move the actual
files that they represent.

Unifies the way of updating files from wiki info or from a plain json file.

:author: Doug Skrypa
"""

from __future__ import annotations

import json
import logging
import re
from abc import ABC
from datetime import datetime, date
from itertools import chain
from pathlib import Path
from string import capwords
from typing import Union, Optional, Mapping, Any, Iterator, Collection, Generic, TypeVar, Callable, Type, overload

from PIL import Image

from ds_tools.caching.decorators import cached_property
from ds_tools.fs.paths import Paths
from ds_tools.images.compare import ComparableImage
from ds_tools.output import colored

from ..common.disco_entry import DiscoEntryType
from ..common.ratings import stars_to_256
from ..files.album import iter_album_dirs, AlbumDir
from ..files.changes import get_common_changes
from ..files.paths import SafePath
from ..files.track.track import SongFile

__all__ = ['TrackInfo', 'AlbumInfo']
log = logging.getLogger(__name__)

ARTIST_TYPE_DIRS = SafePath('{artist}/{type_dir}')
SOLO_DIR_FORMAT = SafePath('{artist}/Solo/{singer}')
TRACK_NAME_FORMAT = SafePath('{num:02d}. {track}.{ext}')
MULTI_DISK_TRACK_NAME_FORMAT = SafePath('{disk:02d}-{num:02d}. {track}.{ext}')
UPPER_CHAIN_SEARCH = re.compile(r'[A-Z]{2,}').search

T = TypeVar('T')
D = TypeVar('D')
StrOrStrs = Union[str, Collection[str]]


def parse_date(dt_str: str | date | None) -> Optional[date]:
    if dt_str is None or isinstance(dt_str, date):
        return dt_str
    for fmt in ('%Y%m%d', '%Y-%m-%d', '%Y.%m.%d', '%Y'):
        try:
            return datetime.strptime(dt_str, fmt).date()
        except ValueError:
            pass
    return None


class GenreMixin:
    def add_genre(self, genre: str):
        genre_set = self.genre_set
        genre_set.add(genre)
        self.genre = genre_set  # noqa

    @property
    def genre_set(self) -> set[str]:
        if genre := self.genre:  # noqa
            return {genre} if isinstance(genre, str) else set(genre)
        else:
            return set()

    def genre_list(self, title_case: bool = False) -> list[str]:
        return self.norm_genres() if title_case else sorted(self.genre_set)

    def norm_genres(self) -> list[str]:
        return [normalize_case(genre) for genre in sorted(self.genre_set)]


class Serializable(ABC):
    _fields: dict[str, Field]

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls._init_fields()

    @classmethod
    def _init_fields(cls):
        if '_Serializable__fields_initialized' not in cls.__dict__:
            cls.__fields_initialized = True
            cls._fields = {}

    def __init__(self, **kwargs):
        self.update(**kwargs)

    def update(self, **kwargs):
        if bad := ', '.join(map(repr, (k for k in kwargs if k not in self._fields))):
            raise KeyError(f'Invalid {self.__class__.__name__} keys/attributes: {bad}')
        for key, val in kwargs.items():
            setattr(self, key, val)


class Field(Generic[T, D]):
    __slots__ = ('name', 'type', 'default', 'default_factory')
    name: str
    type: Callable[[Any], T]
    default: D
    default_factory: Callable[[], D]

    def __init__(
        self, type: Callable[[Any], T] = None, default: D = None, default_factory: Callable[[], D] = None  # noqa
    ):
        self.type = type
        self.default = default
        self.default_factory = default_factory

    def __set_name__(self, owner: Type[Serializable], name: str):
        self.name = name
        owner._init_fields()
        owner._fields[name] = self

    def __get__(self, instance: Serializable | None, owner: Type[Serializable]) -> Field | T | D:
        if instance is None:
            return self
        try:
            return instance.__dict__[self.name]
        except KeyError:
            if factory := self.default_factory:
                instance.__dict__[self.name] = value = factory()
                return value
            return self.default

    def __set__(self, instance: Serializable, value: Any):
        if (type_func := self.type) is not None:
            if type_func in {int, str, float} and value in (None, ''):
                value = None
            else:
                value = type_func(value)
        instance.__dict__[self.name] = value


class TrackInfo(Serializable, GenreMixin):
    # region Track Fields & Init
    # fmt: off
    album: AlbumInfo                            # The AlbumInfo that this track is in
    title: str = Field(str)                     # Track title (tag)
    artist: str = Field(str)                    # Artist name (if different than the album artist)
    num: int = Field(int)                       # Track number
    genre: StrOrStrs = Field()                  # Track genre
    rating: int = Field(int)                    # Rating out of 10
    name: str = Field(str)                      # File name to be used
    disk: int = Field(int)                      # The disk from which this track originated (if different than album's)
    # fmt: on

    @overload
    def __init__(
        self,
        album: AlbumInfo,
        *,
        title: str = None,
        artist: str = None,
        num: int = None,
        genre: StrOrStrs = None,
        rating: int = None,
        name: str = None,
        disk: int = None,
    ):
        ...

    def __init__(self, album: AlbumInfo, **kwargs):
        self.album = album
        super().__init__(**kwargs)

    @classmethod
    def _from_file(cls, track: SongFile, album: AlbumInfo) -> TrackInfo:
        return cls(
            album,
            title=track.tag_title,
            artist=track.tag_artist,
            num=track.track_num,
            genre=track.tag_genres,
            rating=track.star_rating_10,
            disk=track.disk_num,
        )

    @classmethod
    def from_file(cls, track: SongFile, album: AlbumInfo = None) -> TrackInfo:
        if album is None:
            album = AlbumInfo.from_album_dir(AlbumDir(track.path.parent))
        return album.tracks[track.path.as_posix()]

    # endregion

    @cached_property
    def path(self) -> Path:
        # Far from ideal, but a better solution would require more changes to other places in the code at this point
        for path, track_info in self.album.tracks.items():
            if track_info is self:
                return Path(path)

    @cached_property
    def mp4(self) -> bool:
        if self.album.mp4:
            return True
        elif len({t.path.suffix for t in self.album.tracks.values()}) == 1:
            return False
        elif self.path.exists():
            return SongFile(self.path).tag_type == 'mp4'
        return self.path.suffix.lower() == '.mp4'

    def to_dict(self, title_case: bool = False) -> dict[str, Any]:
        if title_case:
            return {
                'artist': normalize_case(self.artist) if self.artist else self.artist,
                'title': normalize_case(self.title) if self.title else self.title,
                'name': normalize_case(self.name) if self.name else self.name,
                'num': self.num,
                'genre': self.norm_genres(),
                'rating': self.rating,
                'disk': self.disk,
            }
        else:
            return {
                'title': self.title,
                'artist': self.artist,
                'num': self.num,
                'name': self.name,
                'genre': self.genre_list(),
                'rating': self.rating,
                'disk': self.disk,
            }

    def tags(self) -> dict[str, Any]:
        album = self.album
        disk = self.disk or album.disk
        tags = {
            'title': self.title,
            'artist': self.artist or album.artist,
            'track': (self.num, len(album.tracks)) if self.mp4 else self.num,
            'date': album.date.strftime('%Y%m%d') if album.date else None,  # noqa
            'genre': list(filter(None, self.genre_set.union(album.genre_set))) or None,
            'album': album.title,
            'album_artist': album.artist,
            'disk': (disk, album.disks) if self.mp4 else disk,
            'wiki:album': album.wiki_album,
            'wiki:artist': album.wiki_artist,
        }
        if (rating := self.rating) is not None:
            tags['rating'] = stars_to_256(rating, 10)
        return {k: v for k, v in tags.items() if v is not None}

    def expected_name(self, file: SongFile) -> str:
        if _disks := self.album.disks:
            try:
                disks = int(_disks)
            except (TypeError, ValueError):
                disks = 0
        else:
            disks = 0

        if disk := self.disk or self.album.disk:
            try:
                disk = int(disk)
            except (TypeError, ValueError):
                disk = 1
        else:
            disk = 1
        formatter = MULTI_DISK_TRACK_NAME_FORMAT if disks > 1 else TRACK_NAME_FORMAT
        return formatter(track=self.name or self.title, ext=file.ext, num=int(self.num), disk=disk)

    def maybe_rename(self, file: SongFile, dry_run: bool = False):
        filename = self.expected_name(file)
        if file.path.name != filename:
            prefix = '[DRY RUN] Would rename' if dry_run else 'Renaming'
            rel_path = Path(file.rel_path)
            log.info(f'{prefix} {rel_path.parent}/{colored(rel_path.name, 11)} -> {colored(filename, 10)}')
            if not dry_run:
                file.rename(file.path.with_name(filename))


def _normalize_type(value: str | DiscoEntryType | None) -> DiscoEntryType:
    if value is None:
        return DiscoEntryType.UNKNOWN
    return value if isinstance(value, DiscoEntryType) else DiscoEntryType.for_name(value)


TrackMap = dict[str, TrackInfo]


class AlbumInfo(Serializable, GenreMixin):
    # fmt: off
    title: str = Field(str)                         # Album title (tag)
    artist: str = Field(str)                        # Album artist name
    date: date | None = Field(parse_date)           # Album release date
    disk: int = Field(int)                          # Disk number
    genre: StrOrStrs = Field(lambda x: x)           # Album genre
    tracks: TrackMap = Field(default_factory=dict)  # Mapping of {path: TrackInfo} for this album's tracks
    name: str = Field(str)                          # Directory name to be used
    parent: str = Field(str)                        # Artist name to use in file paths
    singer: str = Field(str)                        # Solo singer when in a group, to be sorted under that group
    solo_of_group: bool = Field(bool, False)        # Whether the singer is a soloist
    type: DiscoEntryType = Field(_normalize_type, DiscoEntryType.UNKNOWN)  # single, album, mini album, etc.
    number: int = Field(int)                        # This album is the Xth of its type from this artist
    numbered_type: str = Field(str)                 # The type + number within that type for this artist
    disks: int = Field(int, 1)                      # Total number of disks for this album
    mp4: bool = Field(bool, False)                  # Whether the files in this album are mp4s
    cover_path: str = Field(str)                    # Path to a cover image
    cover_max_width: int = Field(int, 1200)         # Maximum width for new cover images
    wiki_album: str = Field(str)                    # URL of the Wiki page that this album matches
    wiki_artist: str = Field(str)                   # URL of the Wiki page that this album's artist matches
    kpop_gen: float = Field(float)                  # K-Pop generation
    # fmt: on

    @property
    def ost(self):
        return self.type is DiscoEntryType.Soundtrack

    @property
    def album_dir(self) -> AlbumDir:
        paths = {Path(path).parent for path in self.tracks}
        if len(paths) == 1:
            return AlbumDir(next(iter(paths)))
        elif not paths:
            raise ValueError('No parent paths were found')
        raise ValueError(f'Found multiple parent paths: {sorted(paths)}')

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> AlbumInfo:
        kwargs = {key: val for key, val in data.items() if key in cls._fields and key != 'tracks'}
        self = cls(**kwargs)
        if tracks := data.get('tracks'):
            self.tracks = {path: TrackInfo(self, **track) for path, track in tracks.items()}
        self.name = self.name or self.title
        return self

    def to_dict(self, title_case: bool = False):
        normalized = {
            'date': self.date.strftime('%Y-%m-%d') if self.date else None,  # noqa
            'tracks': {path: track.to_dict(title_case) for path, track in self.tracks.items()},
            'type': self.type.real_name if self.type else None,
            'genre': self.genre_list(title_case),
        }

        data = {key: normalized.get(key, getattr(self, key)) for key in self._fields}
        if title_case:
            for key in ('title', 'artist', 'name', 'parent', 'singer'):
                if value := data[key]:
                    data[key] = normalize_case(value)
        return data

    def copy(self) -> AlbumInfo:
        return self.from_dict(self.to_dict())

    @classmethod
    def from_album_dir(cls, album_dir: AlbumDir) -> AlbumInfo:
        file = next(iter(album_dir))  # type: SongFile
        genres = set(chain.from_iterable(f.tag_genres for f in album_dir))
        self = cls(
            title=file.tag_album,
            artist=file.tag_album_artist,
            date=file.date,
            disk=file.disk_num,
            genre=next(iter(genres)) if len(genres) == 1 else None,
            name=file.tag_album,
            parent=file.tag_album_artist,
            mp4=all(f.tag_type == 'mp4' for f in album_dir),
            wiki_album=file.album_url,
            wiki_artist=file.artist_url,
        )
        self.tracks = {f.path.as_posix(): TrackInfo._from_file(f, self) for f in album_dir}
        return self

    @classmethod
    def from_paths(cls, path_or_paths: Paths) -> Iterator[AlbumInfo]:
        for album_dir in iter_album_dirs(path_or_paths):
            yield cls.from_album_dir(album_dir)

    @classmethod
    def from_path(cls, path: Union[str, Path]) -> AlbumInfo:
        album_dir = next(iter_album_dirs(path))
        return cls.from_album_dir(album_dir)

    def dump(self, path: Union[str, Path], title_case: bool = False):
        path = Path(path)
        if not path.parent.exists():
            path.parent.mkdir(parents=True)

        log.info(f'Dumping album info to {path}')
        with path.open('w', encoding='utf-8', newline='\n') as f:
            json.dump(self.to_dict(title_case), f, sort_keys=True, indent=4, ensure_ascii=False)

    @classmethod
    def load(cls, path: Union[str, Path]) -> AlbumInfo:
        path = Path(path)
        if not path.is_file():
            raise ValueError(f'Invalid album info path: {path}')
        with path.open('r', encoding='utf-8') as f:
            data = json.load(f)
        return cls.from_dict(data)

    def get_file_info_map(self, album_dir: AlbumDir) -> dict[SongFile, TrackInfo]:
        try:
            return {file: self.tracks[file.path.as_posix()] for file in album_dir}
        except KeyError as e:
            raise ValueError(f'Invalid {self.__class__.__name__} for {album_dir} - missing one more more files: {e}')

    def update_and_move(
        self,
        album_dir: Optional[AlbumDir] = None,
        dest_base_dir: Optional[Path] = None,
        dry_run: bool = False,
        no_album_move: bool = False,
        add_genre: bool = True,
    ):
        album_dir = album_dir or self.album_dir
        if self.tracks:
            self.update_tracks(album_dir, dry_run, add_genre)
        if not no_album_move:
            self.move_album(album_dir, dest_base_dir, dry_run)

    def get_current_cover(self, file_info_map: dict[SongFile, TrackInfo]) -> Optional[Image.Image]:
        try:
            song_file = next(iter(file_info_map))
            return song_file.get_cover_image()
        except Exception as e:
            log.warning(f'Unable to compare the current cover image to {self.cover_path}: {e}')
            return None

    def get_new_cover(self, album_dir: AlbumDir, file_img: Image.Image = None, force: bool = False) -> Image.Image:
        if self.cover_path and (file_img or force):
            log.debug(f'Loading cover image from {self.cover_path}')
            image = Image.open(self.cover_path)
            if not force and ComparableImage(image).is_same_as(ComparableImage(file_img)):
                log.debug(f'The cover image for {album_dir} already matches {self.cover_path}')
                image = None
            else:
                log.info(f'Would update the cover image for {album_dir} to match {self.cover_path}')
        else:
            image = None
        return image

    def _prepare_new_cover(self, album_dir: AlbumDir, image: Image.Image) -> tuple[Image.Image, bytes, str]:
        return album_dir._prepare_cover_image(image, self.cover_max_width)

    def update_tracks(self, album_dir: AlbumDir, dry_run: bool = False, add_genre: bool = True):
        file_info_map = self.get_file_info_map(album_dir)
        file_tag_map = {file: info.tags() for file, info in file_info_map.items()}
        file_img = self.get_current_cover(file_info_map) if self.cover_path else None
        if image := self.get_new_cover(album_dir, file_img):
            image, data, mime_type = self._prepare_new_cover(album_dir, image)
        else:
            image, data, mime_type = None, None, None

        common_changes = get_common_changes(
            album_dir, file_tag_map, extra_newline=True, dry_run=dry_run, add_genre=add_genre
        )
        for file, info in file_info_map.items():
            log.debug(f'Matched {file} to {info.title}')
            file.update_tags(file_tag_map[file], dry_run, no_log=common_changes, add_genre=add_genre)
            if image is not None:
                file._set_cover_data(image, data, mime_type, dry_run)

            info.maybe_rename(file, dry_run)

    @property
    def expected_rel_dir(self) -> str:
        rel_fmt = _album_format(self.date, self.type.numbered and self.number, self.solo_of_group and self.ost)
        rel_fmt = SOLO_DIR_FORMAT + rel_fmt if self.solo_of_group and not self.ost else ARTIST_TYPE_DIRS + rel_fmt
        expected_rel_dir = rel_fmt(
            artist=self.parent,
            type_dir=self.type.directory,
            album_num=self.numbered_type,
            album=self.name,
            date=self.date.strftime('%Y.%m.%d'),  # noqa
            singer=self.singer,
            disk=self.disk,
        )
        return expected_rel_dir

    def dest_base_dir(self, album_dir: AlbumDir, dest_base_dir: Union[Path, str, None] = None) -> Path:
        if dest_base_dir is None:
            expected_parent = Path(self.expected_rel_dir).parent
            log.debug(f'Comparing {expected_parent=} to {album_dir.path.parent.as_posix()}')
            if album_dir.path.parent.as_posix().endswith(expected_parent.as_posix()):
                return album_dir.path.parents[len(expected_parent.parts)]
            else:
                return Path('./sorted_{}'.format(date.today().strftime('%Y-%m-%d')))
        else:
            return Path(dest_base_dir)

    def move_album(self, album_dir: AlbumDir, dest_base_dir: Optional[Path] = None, dry_run: bool = False):
        expected_rel_dir = self.expected_rel_dir
        dest_base_dir = self.dest_base_dir(album_dir, dest_base_dir)

        log.debug(f'Using {expected_rel_dir=}')
        expected_dir = dest_base_dir.joinpath(expected_rel_dir)
        if expected_dir != album_dir.path:
            log.info(f'{"[DRY RUN] Would move" if dry_run else "Moving"} {album_dir} -> {expected_dir.as_posix()}')
            if not dry_run:
                orig_parent_path = album_dir.path.parent
                album_dir.move(expected_dir)
                for path in (orig_parent_path, orig_parent_path.parent):
                    log.log(19, f'Checking directory: {path}')
                    if path.exists() and next(path.iterdir(), None) is None:
                        log.log(19, f'Removing empty directory: {path}')
                        path.rmdir()
        else:
            log.log(19, f'Album {album_dir} is already in the expected dir: {expected_dir}')


def _album_format(date, num, solo_ost):
    if date and num:
        path = SafePath('[{date}] {album} [{album_num}]')
    elif date:
        path = SafePath('[{date}] {album} [{singer} solo]' if solo_ost else '[{date}] {album}')
    elif num:
        path = SafePath('{album} [{album_num}]')
    else:
        path = SafePath('{album} [{singer} solo]' if solo_ost else '{album}')

    return path


def normalize_case(text: str) -> str:
    lc_text = text.lower()
    if (UPPER_CHAIN_SEARCH(text) or lc_text == text) and lc_text != 'ost':
        text = capwords(text)
        # text = text.title().replace("I'M ", "I'm ")
    return text


def fields(serializable: Serializable | Type[Serializable]) -> Iterator[Field]:
    yield from serializable._fields.values()
