"""
:author: Doug Skrypa
"""

import json
import logging
from dataclasses import dataclass, fields, field
from datetime import datetime, date
from functools import partial
from pathlib import Path
from typing import Union, Optional, Dict, Mapping, Any, Iterator

from ds_tools.core import Paths
from ..files import iter_album_dirs, AlbumDir

__all__ = ['TrackInfo', 'AlbumInfo']
log = logging.getLogger(__name__)


def default(cls):
    return partial(field, default_factory=cls)


@dataclass
class TrackInfo:
    # fmt: off
    album: 'AlbumInfo'  # The AlbumInfo that this track is in
    title: str = None   # Track title (tag)
    artist: str = None  # Artist name (if different than the album artist)
    num: int = None     # Track number
    name: str = None    # File name to be used
    # fmt: on

    def to_dict(self):
        return {'title': self.title, 'artist': self.artist, 'num': self.num, 'name': self.name}


@dataclass
class AlbumInfo:
    # fmt: off
    title: str = None                               # Album title (tag)
    artist: str = None                              # Album artist name
    date: date = None                               # Album release date
    disk: int = None                                # Disk number
    genre: str = None                               # Album genre
    tracks: Dict[str, TrackInfo] = default(dict)    # The list of tracks that this album contains
    name: str = None                                # Directory name to be used
    parent: str = None                              # Artist name to use in file paths
    singer: str = None                              # Solo singer when in a group, to be sorted under that group
    type: str = None                                # The album type (single, album, mini album, etc.)
    numbered: bool = False                          # Indicate this album is the Xth of its type from this artist or not
    # fmt: on

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> 'AlbumInfo':
        kwargs = {f.name: data[f.name] for f in fields(cls) if f.name not in ('date', 'tracks')}
        self = cls(**kwargs)
        if date_obj := data.get('date'):
            self.date = date_obj if isinstance(date_obj, date) else parse_date(date_obj)
        if tracks := data.get('tracks'):
            self.tracks = {path: TrackInfo(self, **track) for path, track in tracks.items()}
        return self

    def to_dict(self):
        data = self.__dict__.copy()
        data['date'] = self.date.strftime('%Y-%m-%d')
        data['tracks'] = {path: track.to_dict() for path, track in self.tracks.items()}
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
    def from_paths(cls, paths: Paths) -> Iterator['AlbumInfo']:
        for album_dir in iter_album_dirs(paths):
            yield cls.from_album_dir(album_dir)

    def dump(self, path: Union[str, Path]):
        path = Path(path)
        if not path.parent.exists():
            path.parent.mkdir(parents=True)

        log.info(f'Dumping album info to {path}')
        with path.open('w', encoding='utf-8', newline='\n') as f:
            json.dump(self.to_dict(), f, sort_keys=True, indent=4, ensure_ascii=False)

    @classmethod
    def load(cls, path: Union[str, Path]):
        path = Path(path)
        if not path.is_file():
            raise ValueError(f'Invalid album info path: {path}')
        with path.open('r', encoding='utf-8') as f:
            data = json.load(f)
        return cls.from_dict(data)


def parse_date(dt_str: str) -> Optional[date]:
    for fmt in ('%Y%m%d', '%Y-%m-%d', '%Y.%m.%d', '%Y'):
        try:
            return datetime.strptime(dt_str, fmt).date()
        except ValueError:
            pass
    return None
