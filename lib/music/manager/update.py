"""
Classes representing tracks and albums, with methods to load from file or save to file, and to update/move the actual
files that they represent.

Unifies the way of updating files from wiki info or from a plain json file.

:author: Doug Skrypa
"""

import json
import logging
from dataclasses import dataclass, fields, field
from datetime import datetime, date
from pathlib import Path
from typing import Union, Optional, Dict, Mapping, Any, Iterator, Tuple

from ds_tools.core import Paths
from ds_tools.output import colored
from ..common.disco_entry import DiscoEntryType
from ..files import iter_album_dirs, AlbumDir, SongFile, SafePath, get_common_changes

__all__ = ['TrackInfo', 'AlbumInfo']
log = logging.getLogger(__name__)

ARTIST_TYPE_DIRS = SafePath('{artist}/{type_dir}')
SOLO_DIR_FORMAT = SafePath('{artist}/Solo/{singer}')
TRACK_NAME_FORMAT = SafePath('{num:02d}. {track}.{ext}')


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

    def to_dict(self) -> Dict[str, Any]:
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
    type: DiscoEntryType = None                     # The album type (single, album, mini album, etc.)
    number: int = None                              # This album is the Xth of its type from this artist
    numbered_type: str = None                       # The type + number within that type for this artist
    disks: int = 1                                  # Total number of disks for this album
    mp4: bool = False                               # Whether the files in this album are mp4s
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
        return self

    def to_dict(self):
        data = self.__dict__.copy()
        data['date'] = self.date.strftime('%Y-%m-%d')
        data['tracks'] = {path: track.to_dict() for path, track in self.tracks.items()}
        data['type'] = self.type.real_name if self.type is not None else None
        return data

    @classmethod
    def from_album_dir(cls, album_dir: AlbumDir) -> 'AlbumInfo':
        file = next(iter(album_dir))
        self = cls(file.tag_album, file.tag_album_artist, file.date, file.disk_num)
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

    def dump(self, path: Union[str, Path]):
        path = Path(path)
        if not path.parent.exists():
            path.parent.mkdir(parents=True)

        log.info(f'Dumping album info to {path}')
        with path.open('w', encoding='utf-8', newline='\n') as f:
            json.dump(self.to_dict(), f, sort_keys=True, indent=4, ensure_ascii=False)

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

    def update_and_move(self, album_dir: AlbumDir, dest_base_dir: Optional[Path] = None, dry_run: bool = False):
        if self.tracks:
            self.update_tracks(album_dir, dry_run)
        self.move_album(album_dir, dest_base_dir, dry_run)

    def update_tracks(self, album_dir: AlbumDir, dry_run: bool = False):
        file_info_map = self.get_file_info_map(album_dir)
        file_tag_map = {file: info.tags() for file, info in file_info_map.items()}
        common_changes = get_common_changes(album_dir, file_tag_map, extra_newline=True, dry_run=dry_run)

        for file, info in file_info_map.items():
            log.debug(f'Matched {file} to {info.title}')
            file.update_tags(file_tag_map[file], dry_run, no_log=common_changes)
            maybe_rename_track(file, info.name, info.num, dry_run)

    def move_album(self, album_dir: AlbumDir, dest_base_dir: Optional[Path] = None, dry_run: bool = False):
        rel_fmt = _album_format(
            self.date, self.type.numbered and self.number, self.solo_of_group and self.ost, self.disks, self.ost
        )
        if dest_base_dir is None:
            dest_base_dir = album_dir.path.parent
        else:
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
        expected_dir = dest_base_dir.joinpath(expected_rel_dir)
        if expected_dir != album_dir.path:
            log.info(f'{"[DRY RUN] Would move" if dry_run else "Moving"} {album_dir} -> {expected_dir}')
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
