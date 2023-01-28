"""
Read directly from a copy of Plex's Sqlite3 DB.
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from contextlib import closing
from datetime import datetime
from enum import Enum
from functools import cached_property
from pathlib import Path
from sqlite3 import Row, connect
from typing import TYPE_CHECKING, Union, Iterable, Any
from urllib.parse import parse_qsl, parse_qs

from paramiko import SSHClient, AutoAddPolicy
from scp import SCPClient

from ds_tools.fs.paths import get_user_temp_dir

from music.common.utils import MissingMixin
from .config import config

if TYPE_CHECKING:
    from plexapi.audio import Track
    from .server import LocalPlexServer

__all__ = ['PlexDB', 'StreamType']
log = logging.getLogger(__name__)

DEFAULT_FILE_NAME = 'com.plexapp.plugins.library.db'

# region Enums


class StreamType(MissingMixin, Enum):
    VIDEO = 1
    AUDIO = 2
    SUBTITLE = 3
    LYRIC = 4


class MetaType(MissingMixin, Enum):
    # These match the values in `from plexapi.utils import SEARCHTYPES`
    MOVIE = 1
    SHOW = 2
    SEASON = 3
    EPISODE = 4
    ARTIST = 8
    ALBUM = 9
    TRACK = 10

    @property
    def alias(self) -> str:
        return self.name.lower() + 's'


Stream_Type = Union[StreamType, str, int]
Meta_Type = Union[MetaType, str, int]

# endregion


class PlexDB:
    def __init__(self, db_path: Union[str, Path], execute_log_level: int = 9):
        db_path = Path(db_path).expanduser().resolve()
        self.db_path = db_path
        self.db = connect(db_path.as_posix())
        self.db.row_factory = Row
        self.db.create_function('num_loudness_keys', 1, num_loudness_keys, deterministic=True)
        self.db.create_function('video_height_lte_720', 1, video_height_lte_720, deterministic=True)
        self.db.create_function('video_resolution', 1, video_resolution, deterministic=True)
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

    def find_stream_data(
        self, stream_type: Stream_Type, metadata_type: Union[str, int], metadata_item_id: Union[str, int] = None
    ):
        stream_type = StreamType(stream_type).value
        params = (stream_type, metadata_type, metadata_item_id) if metadata_item_id else (stream_type, metadata_type)
        query = (
            'SELECT streams.*'
            ' FROM media_streams AS streams'
            ' INNER JOIN media_items AS items ON items.id = streams.media_item_id'
            ' INNER JOIN metadata_items AS meta ON meta.id = items.metadata_item_id'
            ' WHERE streams.stream_type_id = ?'  # Values can be found in StreamType
            ' AND meta.metadata_type = ?'  # values match those in `from plexapi.utils import SEARCHTYPES`
        )
        if metadata_item_id:
            query += ' AND meta.id = ?'
        return self.execute(query, params)

    # region Movie Methods

    def _find_movies(self, low_resolution: bool = False):
        query = (
            'SELECT'
            ' movies.id AS movie_id,  movies.title AS movie,'
            ' video_resolution(media_streams.extra_data) as resolution,'
            ' media_items.size as size,'
            ' library_sections.id AS lib_section_id,  library_sections.name AS lib_section'
        )
        query += _prepare_from_and_filters(StreamType.VIDEO, MetaType.MOVIE)
        if low_resolution:
            query += ' AND video_height_lte_720(media_streams.extra_data)'
        return self.execute(query)

    def find_low_res_movies(self):
        movies = {}
        for row in self._find_movies(True):
            movie_id, movie, res, size, lib_section_id, lib_section = row
            movies.setdefault(movie, {})[res] = int(size)
        return movies

    # endregion

    # region Show Methods

    def _find_shows(self, low_resolution: bool = False):
        query = (
            'SELECT'
            ' episodes.id AS episode_id,  episodes."index" AS episode_num,  episodes.title AS episode_title,'
            ' seasons.id AS season_id,    seasons."index" AS season_num,'
            ' shows.id AS show_id,        shows.title AS show,'
            ' video_resolution(media_streams.extra_data) as resolution,'
            ' library_sections.id AS lib_section_id, library_sections.name AS lib_section'
        )
        query += _prepare_from_and_filters(StreamType.VIDEO, MetaType.EPISODE, MetaType.SEASON, MetaType.SHOW)
        if low_resolution:
            query += ' AND video_height_lte_720(media_streams.extra_data)'
        return self.execute(query)

    def find_low_res_show_name_map(self) -> dict[str, dict[str, dict[str, Union[str, None]]]]:
        shows = {}
        for row in self._find_shows(True):
            ep_id, ep_num, ep_title, season_id, season_num, show_id, show, res, lib_section_id, lib_section = row
            episode = f'[{ep_num}] {ep_title}'
            shows.setdefault(show, {}).setdefault(season_num, {})[episode] = res
        return shows

    def find_low_res_show_counts(self):
        shows = defaultdict(Counter)
        for row in self._find_shows(False):
            ep_id, ep_num, ep_title, season_id, season_num, show_id, show, res, lib_section_id, lib_section = row
            shows[show][res] += 1

        filtered = {
            show: res_counts
            for show, res_counts in shows.items()
            if max(int(res.split('x', 1)[1]) for res, num in res_counts.items() if res) <= 720
        }
        return filtered

    # endregion

    # region Tracks Missing Analysys

    def _find_tracks_missing_analysis(self):
        query = (
            'SELECT'
            ' tracks.id AS track_id,    tracks."index" AS track_num,  tracks.title AS track_title,'
            ' albums.id AS album_id,    albums.title AS album_title,'
            ' artists.id AS artist_id,  artists.title AS artist,'
            ' library_sections.id AS lib_section_id, library_sections.name AS lib_section'
        )
        query += _prepare_from_and_filters(StreamType.AUDIO, MetaType.TRACK, MetaType.ALBUM, MetaType.ARTIST)
        query += '\nAND num_loudness_keys(media_streams.extra_data) = 0'

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

    # endregion


# region Registered DB Functions


def num_loudness_keys(extra_data: str) -> int:
    return sum(1 for k, v in parse_qsl(extra_data) if k.startswith('ld:'))


def video_height_lte_720(extra_data: str) -> bool:
    try:
        height = int(parse_qs(extra_data)['ma:height'][0])
    except (TypeError, ValueError, IndexError, KeyError):
        return False
    return height <= 720


def video_resolution(extra_data: str) -> Union[str, None]:
    data = parse_qs(extra_data)
    try:
        width = int(data['ma:width'][0])
        height = int(data['ma:height'][0])
    except (TypeError, ValueError, IndexError, KeyError):
        return None
    # Note: Sqlite3 doesn't seem to like returning a tuple of ints
    return f'{width}x{height}'


# endregion


def _prepare_from_and_filters(stream_type: Stream_Type, *metadata_types: Meta_Type) -> str:
    """
    :param stream_type: The type of media stream to search for
    :param metadata_types: One or more metadata types, in order of child, parent, grandparent, etc
    :return: The ``FROM ... JOIN ... WHERE ...`` portion of the query to use for the given types
    """
    stream_type = StreamType(stream_type)
    metadata_types = [MetaType(mt) for mt in metadata_types]

    query = ['', 'FROM media_streams', 'INNER JOIN media_items ON media_items.id = media_streams.media_item_id']

    last = 'media_items'
    for i, mdt in enumerate(metadata_types):
        field = 'parent_id' if i else 'metadata_item_id'
        query.append(f'INNER JOIN metadata_items AS {mdt.alias} ON {mdt.alias}.id = {last}.{field}')
        last = mdt.alias

    query += [
        f'INNER JOIN library_sections ON library_sections.id = {last}.library_section_id',
        f'WHERE media_streams.stream_type_id = {stream_type.value}',
    ]
    query.extend(f'AND {mdt.alias}.metadata_type = {mdt.value}' for mdt in metadata_types)
    return '\n'.join(query)


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
