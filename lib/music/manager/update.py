"""
Classes representing tracks and albums, with methods to load from file or save to file, and to update/move the actual
files that they represent.

Unifies the way of updating files from wiki info or from a plain json file.

:author: Doug Skrypa
"""

import json
import logging
import re
from dataclasses import dataclass, fields, field
from datetime import datetime, date
from pathlib import Path
from typing import Union, Optional, Dict, Mapping, Any, Iterator

from ds_tools.fs.paths import Paths
from ds_tools.images.compare import ComparableImage
from ds_tools.output import colored
from ..common.disco_entry import DiscoEntryType
from ..files.album import iter_album_dirs, AlbumDir
from ..files.changes import get_common_changes
from ..files.paths import SafePath
from ..files.track.track import SongFile
from .images import _jpeg_from_path

__all__ = ['TrackInfo', 'AlbumInfo']
log = logging.getLogger(__name__)

ARTIST_TYPE_DIRS = SafePath('{artist}/{type_dir}')
SOLO_DIR_FORMAT = SafePath('{artist}/Solo/{singer}')
TRACK_NAME_FORMAT = SafePath('{num:02d}. {track}.{ext}')
UPPER_CHAIN_SEARCH = re.compile(r'[A-Z]{2,}').search


def default(cls):
    return field(default_factory=cls)


@dataclass
class TrackInfo:
    # fmt: off
    album: 'AlbumInfo'  # The AlbumInfo that this track is in
    title: str = None   # Track title (tag)
    artist: str = None  # Artist name (if different than the album artist)
    num: int = None     # Track number
    name: str = None    # File name to be used
    # fmt: on

    def to_dict(self, title_case: bool = False) -> Dict[str, Any]:
        if title_case:
            return {
                'artist': normalize_case(self.artist) if self.artist else self.artist,
                'title': normalize_case(self.title) if self.title else self.title,
                'name': normalize_case(self.name) if self.name else self.name,
                'num': self.num,
            }
        else:
            return {'title': self.title, 'artist': self.artist, 'num': self.num, 'name': self.name}

    def tags(self) -> Dict[str, Any]:
        tags = {
            'title': self.title,
            'artist': self.artist or self.album.artist,
            'track': (self.num, len(self.album.tracks)) if self.album.mp4 else self.num,
            'date': self.album.date.strftime('%Y%m%d'),
            'genre': self.album.genre,
            'album': self.album.title,
            'album_artist': self.album.artist,
            'disk': (self.album.disk, self.album.disks) if self.album.mp4 else self.album.disk,
            'wiki:album': self.album.wiki_album,
            'wiki:artist': self.album.wiki_artist,
        }
        return {k: v for k, v in tags.items() if v is not None}


@dataclass
class AlbumInfo:
    # fmt: off
    title: str = None                               # Album title (tag)
    artist: str = None                              # Album artist name
    date: date = None                               # Album release date
    disk: int = None                                # Disk number
    genre: str = None                               # Album genre
    tracks: Dict[str, TrackInfo] = default(dict)    # Mapping of {path: TrackInfo} for the tracks in this album
    name: str = None                                # Directory name to be used
    parent: str = None                              # Artist name to use in file paths
    singer: str = None                              # Solo singer when in a group, to be sorted under that group
    solo_of_group: bool = False                     # Whether the singer is a soloist
    type: DiscoEntryType = DiscoEntryType.UNKNOWN   # The album type (single, album, mini album, etc.)
    number: int = None                              # This album is the Xth of its type from this artist
    numbered_type: str = None                       # The type + number within that type for this artist
    disks: int = 1                                  # Total number of disks for this album
    mp4: bool = False                               # Whether the files in this album are mp4s
    cover_path: str = None                          # Path to a cover image
    cover_max_width: int = 1200                     # Maximum width for new cover images
    wiki_album: str = None                          # URL of the Wiki page that this album matches
    wiki_artist: str = None                         # URL of the Wiki page that this album's artist matches
    kpop_gen: float = None                          # K-Pop generation
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
    def from_dict(cls, data: Mapping[str, Any]) -> 'AlbumInfo':
        kwargs = {f.name: data.get(f.name, f.default) for f in fields(cls) if f.name not in ('date', 'tracks', 'type')}
        self = cls(**kwargs)
        if date_obj := data.get('date'):
            self.date = date_obj if isinstance(date_obj, date) else parse_date(date_obj)
        if tracks := data.get('tracks'):
            self.tracks = {path: TrackInfo(self, **track) for path, track in tracks.items()}
        if entry_type := data.get('type'):
            self.type = DiscoEntryType.for_name(entry_type)
        self.name = self.name or self.title
        return self

    def to_dict(self, title_case: bool = False):
        data = self.__dict__.copy()
        data['date'] = self.date.strftime('%Y-%m-%d')
        data['tracks'] = {path: track.to_dict(title_case) for path, track in self.tracks.items()}
        data['type'] = self.type.real_name if self.type is not None else None
        if title_case:
            for key in ('title', 'artist', 'genre', 'name', 'parent', 'singer'):
                if value := data[key]:
                    data[key] = normalize_case(value)
        return data

    @classmethod
    def from_album_dir(cls, album_dir: AlbumDir) -> 'AlbumInfo':
        file = next(iter(album_dir))  # type: SongFile
        self = cls(
            title=file.tag_album,
            artist=file.tag_album_artist,
            date=file.date,
            disk=file.disk_num,
            genre=file.tag_genre,
            name=file.tag_album,
            parent=file.tag_album_artist,
            mp4=all(f.tag_type == 'mp4' for f in album_dir),
        )
        self.tracks = {
            file.path.as_posix(): TrackInfo(self, file.tag_title, file.tag_artist, file.track_num) for file in album_dir
        }
        return self

    @classmethod
    def from_paths(cls, path_or_paths: Paths) -> Iterator['AlbumInfo']:
        for album_dir in iter_album_dirs(path_or_paths):
            yield cls.from_album_dir(album_dir)

    @classmethod
    def from_path(cls, path: Union[str, Path]) -> 'AlbumInfo':
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
    def load(cls, path: Union[str, Path]) -> 'AlbumInfo':
        path = Path(path)
        if not path.is_file():
            raise ValueError(f'Invalid album info path: {path}')
        with path.open('r', encoding='utf-8') as f:
            data = json.load(f)
        return cls.from_dict(data)

    def get_file_info_map(self, album_dir: AlbumDir) -> Dict[SongFile, TrackInfo]:
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
    ):
        album_dir = album_dir or self.album_dir
        if self.tracks:
            self.update_tracks(album_dir, dry_run)
        if not no_album_move:
            self.move_album(album_dir, dest_base_dir, dry_run)

    def update_tracks(self, album_dir: AlbumDir, dry_run: bool = False):
        file_info_map = self.get_file_info_map(album_dir)
        file_tag_map = {file: info.tags() for file, info in file_info_map.items()}
        if self.cover_path:
            log.debug(f'Loading cover image from {self.cover_path}')
            image, img_data = _jpeg_from_path(self.cover_path, self.cover_max_width)
            try:
                song_file = next(iter(file_info_map))
                file_img = song_file.get_cover_image()
            except Exception as e:
                log.warning(f'Unable to compare the current cover image to {self.cover_path}: {e}')
            else:
                if ComparableImage(image).is_same_as(ComparableImage(file_img)):
                    log.debug(f'The cover image for {album_dir} already matches {self.cover_path}')
                    image, img_data = None, None
                else:
                    log.info(f'Would update the cover image for {album_dir} to match {self.cover_path}')
        else:
            image, img_data = None, None

        common_changes = get_common_changes(album_dir, file_tag_map, extra_newline=True, dry_run=dry_run)
        for file, info in file_info_map.items():
            log.debug(f'Matched {file} to {info.title}')
            file.update_tags(file_tag_map[file], dry_run, no_log=common_changes)
            if image is not None:
                file.set_cover_data(image, dry_run, img_data)
            maybe_rename_track(file, info.name or info.title, info.num, dry_run)

    def move_album(self, album_dir: AlbumDir, dest_base_dir: Optional[Path] = None, dry_run: bool = False):
        rel_fmt = _album_format(
            self.date, self.type.numbered and self.number, self.solo_of_group and self.ost, self.disks, self.ost
        )
        rel_fmt = SOLO_DIR_FORMAT + rel_fmt if self.solo_of_group and not self.ost else ARTIST_TYPE_DIRS + rel_fmt
        expected_rel_dir = rel_fmt(
            artist=self.parent,
            type_dir=self.type.directory,
            album_num=self.numbered_type,
            album=self.name,
            date=self.date.strftime('%Y.%m.%d'),
            singer=self.singer,
            disk=self.disk,
        )

        if dest_base_dir is None:
            expected_parent = Path(expected_rel_dir).parent
            log.debug(f'Comparing {expected_parent=} to {album_dir.path.parent.as_posix()}')
            if album_dir.path.parent.as_posix().endswith(expected_parent.as_posix()):
                dest_base_dir = album_dir.path.parents[len(expected_parent.parts)]
            else:
                dest_base_dir = Path('./sorted_{}'.format(date.today().strftime('%Y-%m-%d')))
        else:
            dest_base_dir = Path(dest_base_dir)

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


def parse_date(dt_str: str) -> Optional[date]:
    for fmt in ('%Y%m%d', '%Y-%m-%d', '%Y.%m.%d', '%Y'):
        try:
            return datetime.strptime(dt_str, fmt).date()
        except ValueError:
            pass
    return None


def _album_format(date, num, solo_ost, disks=1, ost=False):
    if date and num:
        path = SafePath('[{date}] {album} [{album_num}]')
    elif date:
        path = SafePath('[{date}] {album} [{singer} solo]' if solo_ost else '[{date}] {album}')
    elif num:
        path = SafePath('{album} [{album_num}]')
    else:
        path = SafePath('{album} [{singer} solo]' if solo_ost else '{album}')

    if disks and disks > 1 and not ost:
        path += SafePath('Disk {disk}')
    return path


def maybe_rename_track(file: SongFile, track_name: str, num: int, dry_run: bool = False):
    prefix = '[DRY RUN] Would rename' if dry_run else 'Renaming'
    filename = TRACK_NAME_FORMAT(track=track_name, ext=file.ext, num=num)
    if file.path.name != filename:
        rel_path = Path(file.rel_path)
        log.info(f'{prefix} {rel_path.parent}/{colored(rel_path.name, 11)} -> {colored(filename, 10)}')
        if not dry_run:
            file.rename(file.path.with_name(filename))


def normalize_case(text: str) -> str:
    if UPPER_CHAIN_SEARCH(text) or text.lower() == text:
        text = text.title().replace("I'M ", "I'm ")
    return text
