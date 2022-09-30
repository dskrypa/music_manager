"""
Read directly from a copy of Plex's Sqlite3 DB.
"""

from __future__ import annotations

import logging
from contextlib import closing
from datetime import datetime
from enum import Enum
from functools import cached_property
from pathlib import Path
from sqlite3 import Row, connect
from typing import TYPE_CHECKING, Union, Iterable, Any
from urllib.parse import parse_qsl

from paramiko import SSHClient, AutoAddPolicy
from scp import SCPClient

from ds_tools.fs.paths import get_user_temp_dir
# from ds_tools.utils.sqlite3 import Sqlite3Database

from .config import config

if TYPE_CHECKING:
    from plexapi.audio import Track
    from .server import LocalPlexServer

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
        """
        SCPs the db file from the server to a local path, then initializes this class with that file.

        Uses SCP instead of ``PlexServer.downloadDatabases()`` because SCP is faster.  The REST call is relatively slow,
        and requires an extra decompression step.
        """
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

    @cached_property
    def library_sections(self) -> dict[int, dict[str, Any]]:
        return {row['id']: dict(row) for row in self.execute('SELECT * from library_sections')}

    def find_media_streams(self, stream_type: Stream_Type):
        params = (StreamType(stream_type).value,)
        query = 'SELECT id, media_item_id, media_part_id, extra_data FROM media_streams WHERE stream_type_id=?'
        return self.execute(query, params)

    def _find_tracks_missing_analysis(self):
        query = (
            'SELECT'
            ' tracks.id AS track_id,'
            ' tracks."index" AS track_num,'
            ' tracks.title AS track_title,'
            ' albums.id AS album_id,'
            ' albums.title AS album_title,'
            ' artists.id AS artist_id,'
            ' artists.title AS artist,'
            ' library_sections.id AS lib_section_id,'
            ' library_sections.name AS lib_section'
            #
            ' FROM media_streams'
            ' INNER JOIN media_items ON media_items.id = media_streams.media_item_id'
            ' INNER JOIN metadata_items AS tracks ON tracks.id = media_items.metadata_item_id'
            ' INNER JOIN metadata_items AS albums ON albums.id = tracks.parent_id'
            ' INNER JOIN metadata_items AS artists ON artists.id = albums.parent_id'
            ' INNER JOIN library_sections ON library_sections.id = artists.library_section_id'
            # Note: metadata_type values can be found in `from plexapi.utils import SEARCHTYPES`
            ' WHERE media_streams.stream_type_id = 2'  # StreamType.AUDIO.value
            ' AND tracks.metadata_type = 10'  # SEARCHTYPES['track']
            ' AND albums.metadata_type = 9'  # SEARCHTYPES['album']
            ' AND artists.metadata_type = 8'  # SEARCHTYPES['artist']
            ' AND num_loudness_keys(media_streams.extra_data) = 0'
        )
        return self.execute(query)

    def find_missing_analysis_name_map(self) -> dict[str, dict[str, dict[str, list[str]]]]:
        albums = {}
        for row in self._find_tracks_missing_analysis():
            track_id, track_num, track, album_id, album, artist_id, artist, lib_section_id, lib_section = row
            albums.setdefault(lib_section, {}).setdefault(artist, {}).setdefault(album, []).append(track)
        return albums

    def find_missing_analysis_table(self) -> list[dict[str, Any]]:
        columns = (
            'track_id', 'track_num', 'track', 'album_id', 'album', 'artist_id', 'artist', 'section_id', 'lib_section'
        )
        return [dict(zip(columns, row)) for row in self._find_tracks_missing_analysis()]

    def find_missing_analysis_tracks(self, plex: LocalPlexServer) -> dict[int, list[Track]]:
        section_track_ids_map = {}
        for row in self._find_tracks_missing_analysis():
            section_track_ids_map.setdefault(row['lib_section_id'], []).append(row['track_id'])

        section_tracks_map = {}
        for section_id, track_ids in section_track_ids_map.items():
            section = plex.get_lib_section(section_id)
            section_tracks_map[section.title] = [section.fetchItem(tid) for tid in track_ids]
        return section_tracks_map


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
