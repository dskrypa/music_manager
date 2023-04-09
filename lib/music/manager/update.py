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
from collections import Counter
from datetime import datetime, date
from pathlib import Path
from string import capwords
from typing import TYPE_CHECKING, Union, Mapping, Any, Iterator, Collection, Generic, TypeVar, Callable, Type, overload

from ordered_set import OrderedSet
from PIL.Image import Image as PILImage, open as open_image

from ds_tools.caching.decorators import cached_property
from ds_tools.fs.paths import Paths
from ds_tools.images.compare import ComparableImage
from ds_tools.output import colored

from music.common.disco_entry import DiscoEntryType
from music.common.ratings import stars_to_256
from music.files.album import iter_album_dirs, AlbumDir
from music.files.changes import get_common_changes
from music.files.cover import prepare_cover_image
from music.files.paths import SafePath
from music.files.track.track import SongFile
from music.text.name import Name

if TYPE_CHECKING:
    from music.typing import PathLike

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
ImageTuple = tuple[PILImage, bytes, str] | tuple[None, None, None]


def parse_date(dt_str: str | date | None) -> date | None:
    if dt_str is None or isinstance(dt_str, date):
        return dt_str
    for fmt in ('%Y%m%d', '%Y-%m-%d', '%Y.%m.%d', '%Y'):
        try:
            return datetime.strptime(dt_str, fmt).date()
        except ValueError:
            pass
    return None


class GenreMixin:
    genre: StrOrStrs

    def add_genre(self, genre: str):
        genre_set = self.genre_set
        genre_set.add(genre)
        self.genre = genre_set

    @property
    def genre_set(self) -> set[str]:
        if genre := self.genre:
            return {genre} if isinstance(genre, str) else set(genre)
        else:
            return set()

    def get_genre_set(self, title_case: bool = False) -> set[str]:
        if title_case:
            return {normalize_case(genre) for genre in self.genre_set}
        else:
            return self.genre_set

    def genre_list(self, title_case: bool = False) -> list[str]:
        return self.norm_genres() if title_case else sorted(self.genre_set)

    def norm_genres(self) -> list[str]:
        return [normalize_case(genre) for genre in sorted(self.genre_set)]


class Serializable(ABC):
    _fields: dict[str, Field]
    _cmp_fields: set[str]

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls._init_fields()

    @classmethod
    def _init_fields(cls):
        if '_Serializable__fields_initialized' not in cls.__dict__:
            cls.__fields_initialized = True
            cls._fields = {}
            cls._cmp_fields = set()

    def __init__(self, **kwargs):
        self.update(**kwargs)
        self.__modified = False

    def update(self, **kwargs):
        if bad := ', '.join(map(repr, (k for k in kwargs if k not in self._fields))):
            raise KeyError(f'Invalid {self.__class__.__name__} keys/attributes: {bad}')
        for key, val in kwargs.items():
            setattr(self, key, val)

    def __getitem__(self, field: str):
        if field in self._fields:
            return getattr(self, field)
        raise KeyError(f'Invalid {field=}')

    def __setitem__(self, field: str, value):
        if field not in self._fields:
            raise KeyError(f'Invalid {field=}')
        self.__modified = True
        setattr(self, field, value)

    def update_from_old_new_tuples(self, key_change_map: Mapping[str, tuple[Any, Any]]):
        for key, (old_val, new_val) in key_change_map.items():
            self[key] = new_val

    @property
    def was_modified(self) -> bool:
        return self.__modified

    def update_from(self, other: Serializable, skip: Collection[str] = ()):
        if not isinstance(other, self.__class__):
            raise TypeError(f'Unable to update {self} from an object of type={other.__class__.__name__}')
        for key, field in self._fields.items():
            if not (field.read_only or key in skip):
                self[key] = other[key]

    def __ior__(self, other: Serializable):
        self.update_from(other)
        return self


class Field(Generic[T, D]):
    __slots__ = ('name', 'type', 'default', 'default_factory', 'read_only')
    name: str
    type: Callable[[Any], T]
    default: D
    default_factory: Callable[[], D]

    def __init__(
        self,
        type: Callable[[Any], T] = None,  # noqa
        default: D = None,
        default_factory: Callable[[], D] = None,
        read_only: bool = False,
    ):
        self.type = type
        self.default = default
        self.default_factory = default_factory
        self.read_only = read_only

    def __set_name__(self, owner: Type[Serializable], name: str):
        self.name = name
        owner._init_fields()
        owner._fields[name] = self
        if name not in ('genre', 'tracks'):
            owner._cmp_fields.add(name)

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
    rating: int | None = Field(int)             # Rating out of 10
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

    def __eq__(self, other: TrackInfo) -> bool:
        if not isinstance(other, TrackInfo) or self.get_genre_set() != other.get_genre_set():
            return False
        return all(getattr(self, field) == getattr(other, field) for field in self._cmp_fields)

    def __repr__(self) -> str:
        kw_str = ', '.join(f'{k}={getattr(self, k)!r}' for k in self._fields)
        return f'<{self.__class__.__name__}[{kw_str}]>'

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

    def get_all_genres(self, title_case: bool = False) -> set[str]:
        genres = self.get_genre_set(title_case) | self.album.get_genre_set(title_case)
        return {genre for genre in genres if genre}

    def to_dict(self, title_case: bool = False, genres_as_set: bool = False) -> dict[str, Any]:
        if title_case:
            return {
                'artist': normalize_case(self.artist) if self.artist else self.artist,
                'title': normalize_case(self.title) if self.title else self.title,
                'name': normalize_case(self.name) if self.name else self.name,
                'num': self.num,
                'genre': self.get_genre_set(title_case) if genres_as_set else self.norm_genres(),
                'rating': self.rating,
                'disk': self.disk,
            }
        else:
            return {
                'title': self.title,
                'artist': self.artist,
                'num': self.num,
                'name': self.name,
                'genre': self.get_genre_set(title_case) if genres_as_set else self.genre_list(),
                'rating': self.rating,
                'disk': self.disk,
            }

    def tags(self, title_case: bool = False) -> dict[str, Any]:
        album = self.album
        disk = self.disk or album.disk
        tags = {
            'title': self.title,
            'artist': self.artist or album.artist,
            'track': (self.num, len(album.tracks)) if self.mp4 else self.num,
            'date': album.date.strftime('%Y%m%d') if album.date else None,  # noqa
            'genre': sorted(self.get_all_genres(title_case)),
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


TrackMap = dict[str, TrackInfo]


class AlbumInfo(Serializable, GenreMixin):
    _album_dir: AlbumDir
    # region Fields
    title: str = Field(str)                         # Album title (tag)
    artist: str = Field(str)                        # Album artist name

    date: date | None = Field(parse_date)           # Album release date
    disk: int = Field(int)                          # Disk number
    disks: int = Field(int, 1)                      # Total number of disks for this album
    genre: StrOrStrs = Field()                      # Album genre

    name: str = Field(str)                          # Directory name to be used
    parent: str = Field(str)                        # Artist name to use in file paths
    singer: str = Field(str)                        # Solo singer when in a group, to be sorted under that group
    solo_of_group: bool = Field(bool, False)        # Whether the singer is a soloist

    type: DiscoEntryType = Field(DiscoEntryType, DiscoEntryType.UNKNOWN)  # single, album, mini album, etc.
    number: int = Field(int)                        # This album is the Xth of its type from this artist
    numbered_type: str = Field(str)                 # The type + number within that type for this artist

    mp4: bool = Field(bool, False, read_only=True)  # Whether the files in this album are mp4s
    cover_path: str = Field(str)                    # Path to a cover image
    cover_max_width: int = Field(int, 1200)         # Maximum width for new cover images
    wiki_album: str = Field(str)                    # URL of the Wiki page that this album matches
    wiki_artist: str = Field(str)                   # URL of the Wiki page that this album's artist matches
    kpop_gen: float = Field(float)                  # K-Pop generation
    tracks: TrackMap = Field(default_factory=dict)  # Mapping of {path: TrackInfo} for this album's tracks
    # endregion

    def __repr__(self) -> str:
        title, artist = self.title, self.artist
        return f'<{self.__class__.__name__}[{title=}, {artist=}]>'

    def __eq__(self, other: AlbumInfo) -> bool:
        if not isinstance(other, AlbumInfo) or self.get_genre_set() != other.get_genre_set():
            return False
        return all(getattr(self, f) == getattr(other, f) for f in self._cmp_fields) and self.tracks == other.tracks

    def clean(self, force: bool = False) -> AlbumInfo:
        if force or self.was_modified:
            log.debug(f'Returning a clean AlbumInfo instance for {self}')
            album_dir = self.album_dir
            album_dir.refresh()
            return self.from_album_dir(album_dir)
        return self

    def copy(self) -> AlbumInfo:
        return self.from_dict(self.to_dict())

    def update_from(self, other: AlbumInfo, skip: Collection[str] = ()):
        super().update_from(other, {'tracks', *skip})
        if 'tracks' not in skip:
            for s_track, o_track in zip(self.tracks.values(), other.tracks.values()):
                s_track.update_from(o_track)

    def __or__(self, other: AlbumInfo) -> AlbumInfo:
        clone = self.copy()
        clone.update_from(other)
        return clone

    # region Calculated / Custom Properties

    @property
    def was_modified(self) -> bool:
        return super().was_modified or any(t.was_modified for t in self.tracks.values())

    @property
    def ost(self):
        return self.type is DiscoEntryType.Soundtrack

    @property
    def album_dir(self) -> AlbumDir:
        try:
            return self._album_dir
        except AttributeError:
            pass

        paths = {Path(path).parent for path in self.tracks}
        if len(paths) == 1:
            self._album_dir = album_dir = AlbumDir(next(iter(paths)))
            return album_dir
        elif not paths:
            raise ValueError('No parent paths were found')
        raise ValueError(f'Found multiple parent paths: {sorted(paths)}')

    @album_dir.setter
    def album_dir(self, value: AlbumDir | PathLike):
        if not isinstance(value, AlbumDir):
            value = AlbumDir(value)
        track_dirs = {Path(path).parent for path in self.tracks}
        if len(track_dirs) != 1:
            raise ValueError(f'Unable to validate path - found multiple track parent paths: {sorted(track_dirs)}')
        track_dir: Path = next(iter(track_dirs))
        if track_dir.samefile(value.path):
            self._album_dir = value
        else:
            raise ValueError(
                f"The provided album={value.path.as_posix()!r} does not match this album's dir={track_dir.as_posix()!r}"
            )

    @property
    def path(self) -> Path:
        return self.album_dir.path

    # endregion

    # region Deserialization / Alternate Constructor Classmethods

    @classmethod
    def from_album_dir(cls, album_dir: AlbumDir) -> AlbumInfo:
        file: SongFile = next(iter(album_dir))
        try:
            disco_type, num = DiscoEntryType.with_num_from_album_dir(album_dir.path)
        except TypeError:
            kwargs = {}
        else:
            kwargs = {'type': disco_type, 'number': num, 'numbered_type': disco_type.format(num)}

        self = cls(
            title=file.tag_album,
            artist=file.tag_album_artist,
            date=file.date,
            disk=file.disk_num,
            genre=_common_genres(album_dir),
            name=file.tag_album,
            parent=file.tag_album_artist,
            mp4=all(f.tag_type == 'mp4' for f in album_dir),
            wiki_album=file.album_url,
            wiki_artist=file.artist_url,
            **kwargs,
        )
        self._album_dir = album_dir
        self.tracks = {f.path.as_posix(): TrackInfo._from_file(f, self) for f in album_dir}
        return self

    @classmethod
    def from_paths(cls, path_or_paths: Paths) -> Iterator[AlbumInfo]:
        for album_dir in iter_album_dirs(path_or_paths):
            yield cls.from_album_dir(album_dir)

    @classmethod
    def from_path(cls, path: PathLike) -> AlbumInfo:
        album_dir = next(iter_album_dirs(path))
        return cls.from_album_dir(album_dir)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> AlbumInfo:
        kwargs = {key: val for key, val in data.items() if key in cls._fields and key != 'tracks'}
        self = cls(**kwargs)
        if tracks := data.get('tracks'):
            self.tracks = {path: TrackInfo(self, **track) for path, track in tracks.items()}
        self.name = self.name or self.title
        return self

    @classmethod
    def load(cls, path: PathLike) -> AlbumInfo:
        path = Path(path)
        if not path.is_file():
            raise ValueError(f'Invalid album info path: {path}')
        with path.open('r', encoding='utf-8') as f:
            data = json.load(f)
        return cls.from_dict(data)

    # endregion

    # region Serialization Methods

    def to_dict(self, title_case: bool = False, skip: Collection[str] = None, genres_as_set: bool = False):
        normalized = {
            'date': self.date.strftime('%Y-%m-%d') if self.date else None,
            'tracks': {path: track.to_dict(title_case, genres_as_set) for path, track in self.tracks.items()},
            'type': self.type.real_name if self.type else None,
            'genre': self.get_genre_set(title_case) if genres_as_set else self.genre_list(title_case),
        }

        keys = OrderedSet(self._fields).difference(skip) if skip else self._fields  # noqa
        data = {key: normalized.get(key, getattr(self, key)) for key in keys}
        if title_case:
            for key in ('title', 'artist', 'name', 'parent', 'singer'):
                if value := data[key]:
                    data[key] = normalize_case(value)
        return data

    def dump(self, path: PathLike, title_case: bool = False):
        path = Path(path)
        if not path.parent.exists():
            path.parent.mkdir(parents=True)

        log.info(f'Dumping album info to {path}')
        with path.open('w', encoding='utf-8', newline='\n') as f:
            json.dump(self.to_dict(title_case), f, sort_keys=True, indent=4, ensure_ascii=False)

    # endregion

    def get_file_info_map(self, album_dir: AlbumDir = None) -> dict[SongFile, TrackInfo]:
        if album_dir is None:
            album_dir = self.album_dir
        try:
            return {file: self.tracks[file.path.as_posix()] for file in album_dir}
        except KeyError as e:
            raise ValueError(f'Invalid {self.__class__.__name__} for {album_dir} - missing one more more files: {e}')

    def get_track(self, track_identifier: PathLike | TrackInfo | SongFile) -> TrackInfo:
        if isinstance(track_identifier, (SongFile, TrackInfo)):
            track_identifier = track_identifier.path.as_posix()
        elif isinstance(track_identifier, Path):
            track_identifier = track_identifier.as_posix()
        return self.tracks[track_identifier]

    def all_common_genres(self, title_case: bool = False) -> set[str]:
        album_genres = self.get_genre_set(title_case)
        all_track_genres = Counter(g for ti in self.tracks.values() for g in ti.get_genre_set(title_case))
        n_files = len(self.tracks)
        common_track_genres = {genre for genre, num in all_track_genres.items() if num == n_files}
        return album_genres | common_track_genres

    # region Cover-Related Methods

    def get_current_cover(self, file_info_map: dict[SongFile, TrackInfo]) -> PILImage | None:
        try:
            song_file = next(iter(file_info_map))
            return song_file.get_cover_image()
        except Exception as e:
            log.warning(f'Unable to compare the current cover image to {self.cover_path}: {e}')
            return None

    def _get_new_cover(self, album_dir: AlbumDir, file_img: PILImage = None, force: bool = False) -> PILImage:
        if self.cover_path and (file_img or force):
            log.debug(f'Loading cover image from {self.cover_path}')
            image = open_image(self.cover_path)
            if not force and ComparableImage(image).is_same_as(ComparableImage(file_img)):
                log.debug(f'The cover image for {album_dir} already matches {self.cover_path}')
                image = None
            else:
                log.info(f'Would update the cover image for {album_dir} to match {self.cover_path}')
        else:
            image = None
        return image

    def get_new_cover(self, album_dir: AlbumDir = None, file_img: PILImage = None, force: bool = False) -> ImageTuple:
        if album_dir is None:
            album_dir = self.album_dir
        if image := self._get_new_cover(album_dir, file_img, force):
            return prepare_cover_image(image, {f.tag_type for f in album_dir.songs}, self.cover_max_width)
        else:
            return None, None, None

    # endregion

    # region Target Path Methods

    @cached_property
    def sorter(self) -> AlbumSorter:
        return AlbumSorter(self)

    @property
    def expected_rel_dir(self) -> str:
        return self.sorter.get_expected_rel_dir()

    def dest_base_dir(self, album_dir: AlbumDir, dest_base_dir: PathLike | None = None) -> Path:
        if dest_base_dir is None:
            return self.sorter.get_default_base_dir(album_dir=album_dir)
        else:
            return Path(dest_base_dir)

    def get_new_path(self, new_base_dir: PathLike | None = None, in_place: bool = False) -> Path | None:
        if in_place and new_base_dir:
            raise ValueError(f'Bad argument combo: in_place cannot be used with {new_base_dir=}')
        elif in_place:
            return self.sorter.get_sort_in_place_path()
        else:
            return self.sorter.get_new_path(new_base_dir)

    # endregion

    # region Update & Move Methods

    def update_and_move(
        self,
        album_dir: AlbumDir = None,
        dest_base_dir: Path = None,
        dry_run: bool = False,
        no_album_move: bool = False,
        add_genre: bool = True,
    ):
        if self.tracks:
            self.update_tracks(album_dir or self.album_dir, dry_run, add_genre)
        if not no_album_move:
            self.move_album(album_dir or self.album_dir, dest_base_dir, dry_run)

    def update_tracks(self, album_dir: AlbumDir = None, dry_run: bool = False, add_genre: bool = True):
        if album_dir is None:
            album_dir = self.album_dir
        file_info_map = self.get_file_info_map(album_dir)
        file_tag_map = {file: info.tags() for file, info in file_info_map.items()}
        file_img = self.get_current_cover(file_info_map) if self.cover_path else None
        image, data, mime_type = self.get_new_cover(album_dir, file_img)
        common_changes = get_common_changes(
            album_dir, file_tag_map, extra_newline=True, dry_run=dry_run, add_genre=add_genre
        )
        for file, info in file_info_map.items():
            log.debug(f'Matched {file} to {info.title}')
            file.update_tags(file_tag_map[file], dry_run, no_log=common_changes, add_genre=add_genre)
            if image is not None:
                file._set_cover_data(image, data, mime_type, dry_run)

            info.maybe_rename(file, dry_run)

    def move_album(self, album_dir: AlbumDir, dest_base_dir: Path = None, dry_run: bool = False):
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

    # endregion


class AlbumSorter:
    __slots__ = ('album_info',)

    def __init__(self, album_info: AlbumInfo):
        self.album_info = album_info

    def get_artist_dir(self, base_dir: Path, en_only: bool = False) -> Path:
        artist = self.album_info.parent
        if en_only:
            artist = Name.from_enclosed(artist).english
        return base_dir.joinpath(SafePath('{artist}')(artist=artist))

    def get_expected_name(self) -> str:
        album = self.album_info
        date_value = album.date.strftime('%Y.%m.%d') if album.date else None
        return self._name_format(album_num=album.numbered_type, album=album.name, date=date_value, singer=album.singer)

    def get_expected_rel_dir(self, en_artist_only: bool = False) -> str:
        rel_path_fmt = self._parent_dir_format + self._name_format
        album = self.album_info
        artist = album.parent
        if en_artist_only:
            artist = Name.from_enclosed(artist).english

        date_value = album.date.strftime('%Y.%m.%d') if album.date else None
        return rel_path_fmt(
            artist=artist,
            type_dir=album.type.directory,
            album_num=album.numbered_type,
            album=album.name,
            date=date_value,
            singer=album.singer,
            disk=album.disk,
        )

    @property
    def _parent_dir_format(self) -> SafePath:
        album = self.album_info
        if album.solo_of_group and not album.ost:
            return SOLO_DIR_FORMAT  # SafePath('{artist}/Solo/{singer}')
        else:
            return ARTIST_TYPE_DIRS  # SafePath('{artist}/{type_dir}')

    @property
    def _name_format(self) -> SafePath:
        album = self.album_info
        base = '[{date}] {album}' if album.date else '{album}'
        if album.type.numbered and album.number:
            return SafePath(base + ' [{album_num}]')
        elif album.solo_of_group and album.ost:
            return SafePath(base + ' [{singer} solo]')
        else:
            return SafePath(base)

    def get_sort_in_place_path(self) -> Path | None:
        old_album_path = self.album_info.album_dir.path
        new_album_path = old_album_path.parent.joinpath(self.get_expected_name())
        return new_album_path if new_album_path != old_album_path else None

    def get_new_path(self, new_base_dir: PathLike | None = None, en_artist_only: bool = False) -> Path | None:
        old_album_path = self.album_info.album_dir.path
        if new_base_dir is None:
            new_base_dir = old_album_path.parents[2]
        else:
            new_base_dir = Path(new_base_dir).expanduser()

        new_album_path = new_base_dir.joinpath(self.get_expected_rel_dir(en_artist_only))
        return new_album_path if new_album_path != old_album_path else None

    def get_default_base_dir(self, en_artist_only: bool = False, album_dir: AlbumDir = None) -> Path:
        if album_dir is None:
            album_dir = self.album_info.album_dir
        expected_parent = Path(self.get_expected_rel_dir(en_artist_only)).parent
        log.debug(f'Comparing {expected_parent=} to {album_dir.path.parent.as_posix()}')
        if album_dir.path.parent.as_posix().endswith(expected_parent.as_posix()):
            return album_dir.path.parents[len(expected_parent.parts)]
        else:
            return Path(f'./sorted_{date.today().isoformat()}')


def normalize_case(text: str) -> str:
    lc_text = text.lower()
    if (UPPER_CHAIN_SEARCH(text) or lc_text == text) and lc_text != 'ost':
        text = capwords(text)
        # text = text.title().replace("I'M ", "I'm ")
    return text


def fields(serializable: Serializable | Type[Serializable]) -> Iterator[Field]:
    yield from serializable._fields.values()


def _common_genres(files: Collection[SongFile]) -> set[str]:
    genres = Counter(g for f in files for g in f.tag_genres)
    n_files = len(files)
    return {genre for genre, num in genres.items() if num == n_files}
