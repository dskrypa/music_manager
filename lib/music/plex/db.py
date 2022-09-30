"""
Read directly from a copy of Plex's Sqlite3 DB
"""

from __future__ import annotations

import logging
from contextlib import closing
from datetime import datetime
from enum import Enum
from functools import cached_property
from pathlib import Path
from sqlite3 import Row, connect
from typing import Union, Iterable
from urllib.parse import parse_qsl

from paramiko import SSHClient, AutoAddPolicy
from scp import SCPClient

from ds_tools.fs.paths import get_user_temp_dir

from .config import config

__all__ = ['PlexDB', 'StreamType']
log = logging.getLogger(__name__)

DEFAULT_FILE_NAME = 'com.plexapp.plugins.library.db'


class StreamType(Enum):
    VIDEO = 1
    AUDIO = 2
    SUBTITLE = 3
    LYRIC = 4

    @classmethod
    def _missing_(cls, value) -> StreamType:
        if isinstance(value, str):
            try:
                return cls._member_map_[value.upper()]  # noqa
            except KeyError:
                pass
        return super()._missing_(value)  # noqa


Stream_Type = Union[StreamType, str, int]


class PlexDB:
    def __init__(self, db_path: Union[str, Path], execute_log_level: int = 9):
        db_path = Path(db_path).expanduser().resolve()
        self.db_path = db_path
        self.db = connect(db_path.as_posix())
        self.db.row_factory = Row
        self.db.create_function('num_loudness_keys', 1, num_loudness_keys, deterministic=True)
        self.execute_log_level = execute_log_level

    @classmethod
    def from_remote_server(cls, name: str = DEFAULT_FILE_NAME, max_age: int = 180, **kwargs) -> PlexDB:
        path = get_db_file(name, max_age)
        return cls(path, **kwargs)

    def execute(self, *args, **kwargs):
        """
        Auto commit/rollback on exception via with statement
        :return Cursor: Sqlite3 cursor
        """
        with self.db:
            log.log(self.execute_log_level, 'Executing SQL: {}'.format(', '.join(map('"{}"'.format, args))))
            return self.db.execute(*args, **kwargs)

    @cached_property
    def table_names(self) -> tuple[str]:
        return tuple(self.get_table_names())

    def _table_metadata(self) -> Iterable[Row]:
        return self.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")

    def get_table_names(self) -> list[str]:
        """
        :return list: Names of tables in this DB
        """
        return [row['name'] for row in self._table_metadata()]

    def get_table_info(self):
        return {row['name']: dict(row) for row in self._table_metadata()}

    def __contains__(self, name: str) -> bool:
        return name in self.table_names

    def find_media_streams(self, stream_type: Stream_Type):
        params = (StreamType(stream_type).value,)
        query = 'SELECT id, media_item_id, media_part_id, extra_data FROM media_streams WHERE stream_type_id=?'
        return self.execute(query, params)

    def find_audio_streams_missing_analysis(self) -> dict[str, list[str]]:
        query = (
            'SELECT tracks.title AS track_title, albums.title AS album_title'
            ' FROM media_streams'
            ' INNER JOIN media_items ON media_items.id = media_streams.media_item_id'
            ' INNER JOIN metadata_items AS tracks ON tracks.id = media_items.metadata_item_id'
            ' INNER JOIN metadata_items AS albums ON albums.id = tracks.parent_id'
            # Note: metadata_type values can be found in `from plexapi.utils import SEARCHTYPES`
            ' WHERE media_streams.stream_type_id = 2'               # StreamType.AUDIO.value
            ' AND albums.metadata_type = 9'                         # SEARCHTYPES['album']
            ' AND tracks.metadata_type = 10'                        # SEARCHTYPES['track']
            ' AND num_loudness_keys(media_streams.extra_data) = 0'
        )
        albums = {}
        for row in self.execute(query):
            albums.setdefault(row['album_title'], []).append(row['track_title'])
        return albums


def num_loudness_keys(extra_data: str) -> int:
    return sum(1 for k, v in parse_qsl(extra_data) if k.startswith('ld:'))


def get_db_file(name: str = DEFAULT_FILE_NAME, max_age: int = 180) -> Path:
    path = get_user_temp_dir('plexapi').joinpath(name)
    if path.exists():
        last_mod = datetime.fromtimestamp(path.stat().st_mtime)
        if (datetime.now() - last_mod).total_seconds() < max_age:
            log.debug(f'Using locally cached DB last modified {last_mod.isoformat(" ")} < {max_age:,d}s ago')
            return path
        log.debug(
            'Retrieving new DB file - the locally cached version was'
            f' last modified {last_mod.isoformat(" ")} >= {max_age:,d}s ago'
        )
    else:
        log.debug('Retrieving new DB file - there was no locally cached version')

    scp_db_to_tmp_dir(path, name)
    return path


def scp_db_to_tmp_dir(local_path: Path, name: str):
    remote_path = Path(config.db_remote_dir).joinpath(name).as_posix()

    with closing(SSHClient()) as client:
        client.load_system_host_keys()
        client.set_missing_host_key_policy(AutoAddPolicy())
        client.connect(
            config.db_remote_host, username=config.db_remote_user, key_filename=config.db_ssh_key_path.as_posix()
        )
        with SCPClient(client.get_transport()) as scp:
            scp.get(remote_path, local_path.as_posix())
