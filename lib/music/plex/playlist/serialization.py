"""
Plex playlist management utilities

:author: Doug Skrypa
"""

from __future__ import annotations

import gzip
import json
import logging
from contextlib import contextmanager
from datetime import date
from enum import Enum
from pathlib import Path
from tarfile import TarFile
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Any, Iterable, Iterator, Literal, Mapping, TextIO, TypeGuard
from xml.etree.ElementTree import Element, ElementTree, indent as _indent, tostring, fromstring

from plexapi.audio import Track
from plexapi.playlist import Playlist

from ds_tools.fs.paths import prepare_path, sanitize_file_name, unique_path

from .playlist import PlexPlaylist
from .utils import PlaylistXmlDict, get_plex

if TYPE_CHECKING:
    from music.typing import PathLike
    from ..server import LocalPlexServer

    OptServer = LocalPlexServer | None

__all__ = ['PlaylistSerializer', 'PlaylistLoader']
log = logging.getLogger(__name__)


class PlaylistSerializer:
    __slots__ = ('plex', 'dst_dir', 'compress', 'xml', 'playlists')
    playlists: dict[str, PlexPlaylist]

    def __init__(self, dst_dir: PathLike, plex: OptServer = None, compress: bool = True, xml: bool = False):
        self.plex = get_plex(plex)
        self.dst_dir = Path(dst_dir)
        self.dst_dir.mkdir(parents=True, exist_ok=True)
        self.compress = compress
        self.xml = xml
        self.playlists = self.plex.playlists

    def dump_all(self, separate: bool = False):
        if separate:
            self._dump_separate()
        else:
            self._dump_combined()

    # region Dump to One File

    def _dump_combined(self):
        self._dump(
            self._prepare_combined(),
            dst_dir=self.dst_dir,
            stem='all_plex_playlists',
            log_name=f'{len(self.playlists)} playlists',
            compress=self.compress,
            sanitize=False,
        )

    def _prepare_combined(self) -> str | dict[str, PlaylistXmlDict]:
        if self.xml:
            root = Element('PlexPlaylists')
            root.extend(p.as_xml() for p in self.playlists.values())
            _indent(root)
            root.tail = '\n'
            return tostring(root, encoding='unicode')
        else:
            return {name: playlist.dumps() for name, playlist in self.playlists.items()}  # pre-sorted

    # endregion

    # region Dump to Separate Files

    def _dump_separate(self):
        """
        Dumps each playlist into a separate file in a temporary directory, then either compresses that directory and
        moves the compressed file to the specified location, or moves the directory to the specified location.
        """
        dump_name = f'all_plex_playlists_{date.today().isoformat()}'
        # Specifying `dir` for the temp dir so it's guaranteed to be on the same file system for the rename step
        with TemporaryDirectory(dir=self.dst_dir, prefix='.tmp_plex_playlists_') as tmp:
            playlists_dir = Path(tmp, dump_name)
            playlists_dir.mkdir()
            self._dump_separate_to_dir(playlists_dir)
            if self.compress:
                self._compress_separate(playlists_dir, dump_name)
            else:
                self._rename_separate(playlists_dir, dump_name)

    def _dump_separate_to_dir(self, playlists_dir: Path):
        for name, playlist in self.playlists.items():
            self._dump(
                playlist.dumps_xml() if self.xml else playlist.dumps(),
                dst_dir=playlists_dir,
                stem=name,
                log_name=f'playlist={name!r}',
                log_level=logging.DEBUG,
                compress=False,
                skip_prep=True,
            )

    def _compress_separate(self, playlists_dir: Path, dump_name: str):
        tgz_path = playlists_dir.parent.joinpath(f'{dump_name}.tgz')
        with TarFile.gzopen(tgz_path, 'w') as tf:
            tf.add(playlists_dir, arcname=dump_name)

        dst_path = unique_path(self.dst_dir, dump_name, '.tgz')
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        tgz_path.rename(dst_path)
        log.info(f'Saved {len(self.playlists)} to {dst_path.as_posix()}')

    def _rename_separate(self, playlists_dir: Path, dump_name: str):
        dst_path = unique_path(self.dst_dir, dump_name)
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        playlists_dir.rename(dst_path)
        log.info(f'Saved {len(self.playlists)} to {dst_path.as_posix()}')

    # endregion

    @classmethod
    def _dump(
        cls,
        data: PlaylistXmlDict | dict[str, PlaylistXmlDict] | str,
        dst_dir: PathLike,
        stem: str,
        log_name: Any,
        *,
        log_level: int = logging.INFO,
        compress: bool = True,
        sanitize: bool = True,
        skip_prep: bool = False,
    ):
        if xml := isinstance(data, str):
            ext = '.xml.gz' if compress else '.xml'
        else:
            ext = '.json.gz' if compress else '.json'

        if skip_prep:
            path = Path(dst_dir, sanitize_file_name(stem + ext) if sanitize else f'{stem}{ext}')
        else:
            path = prepare_path(dst_dir, (stem, ext), sanitize=sanitize, add_date=True)

        log.log(log_level, f'Saving {log_name} to {path.as_posix()}')
        with _open_file(path, 'w') as f:
            if xml:
                f.write(data)
            else:
                json.dump(data, f, indent=4, ensure_ascii=False)  # noqa  # PyCharm thinks TextIO != SupportsWrite[str]


class PlaylistLoader:
    __slots__ = ('plex',)

    def __init__(self, plex: OptServer = None):
        self.plex = get_plex(plex)

    # region Load Single Playlist

    def load(self, path: PathLike) -> PlexPlaylist:
        with _open_file(path, 'r') as f:
            if _get_file_type(f) == DataType.JSON:
                return self._load_json(json.load(f))
            else:  # XML
                root = ElementTree(file=f).getroot()
                return self._load(root[0], root[1])

    def loads(self, data: str | PlaylistXmlDict) -> PlexPlaylist:
        if _is_single_playlist(data):
            return self._load_json(data)
        elif DataType.for_string(data) == DataType.JSON:
            return self._load_json(json.loads(data))
        else:  # XML
            root = fromstring(data)
            return self._load(root[0], root[1])

    def _load(self, playlist: Element, tracks: Iterable[Element]) -> PlexPlaylist:
        server = self.plex.server
        # Note: PlexObject incorrectly hints that it expects ElementTree, but it always gets an Element instead
        playlist = Playlist(server, playlist)  # noqa
        playlist._items = [Track(server, track) for track in tracks]  # noqa
        return PlexPlaylist(playlist.title, self.plex, playlist)

    def _load_json(self, data: PlaylistXmlDict) -> PlexPlaylist:
        return self._load(fromstring(data['playlist']), (fromstring(td) for td in data['tracks']))

    # endregion

    # region Load All Playlists

    def load_all(self, path: PathLike) -> dict[str, PlexPlaylist]:
        with _open_file(path, 'r') as f:
            if _get_file_type(f) == DataType.JSON:
                return self._load_all_json(json.load(f), path)
            else:  # XML
                return self._load_all_xml(ElementTree(file=f).getroot(), path)

    def _load_all_json(self, data, file: PathLike) -> dict[str, PlexPlaylist]:
        if _is_single_playlist(data):
            playlist = self._load_json(data)
            return {playlist.name: playlist}
        elif _is_name_playlist_map(data):
            return {name: self._load_json(playlist) for name, playlist in data.items()}
        else:
            raise ValueError(f'Unable to load playlists from {file=} - unexpected format')

    def _load_all_xml(self, root: Element, file: str) -> dict[str, PlexPlaylist]:
        if root.tag == 'PlexPlaylists':
            return {playlist.name: playlist for playlist in (self._load(ele[0], ele[1]) for ele in root)}
        elif root.tag == 'PlexPlaylist':
            playlist = self._load(root[0], root[1])
            return {playlist.name: playlist}
        else:
            raise ValueError(f'Unable to load playlists from {file=} - unexpected root tag={root.tag!r}')

    # endregion


@contextmanager
def _open_file(path: PathLike, mode: Literal['r', 'w']) -> Iterator[TextIO]:
    if not isinstance(path, Path):
        path = Path(path).expanduser()

    if path.suffix == '.gz':
        open_func = gzip.open
        mode = 'rt' if mode == 'r' else 'wt'
    else:
        open_func = open

    with open_func(path, mode, encoding='utf-8') as f:
        yield f


class DataType(Enum):
    JSON = 'json'
    XML = 'xml'

    @classmethod
    def for_string(cls, text: str, file_name: str | None = None) -> DataType:
        try:
            first_char = text[0]
        except IndexError as e:
            for_clause = f'for file={file_name!r}' if file_name else 'for data'
            raise ValueError(f'Unable to determine data type {for_clause} with no text') from e

        if first_char == '<':
            return DataType.XML
        elif first_char == '{':
            return DataType.JSON
        else:
            for_clause = f'for file={file_name!r}' if file_name else 'for data'
            raise ValueError(f'Unable to determine data type {for_clause} with {first_char=}')


def _get_file_type(file: TextIO) -> DataType:
    first_char = file.read(1)
    file.seek(0)  # Reset the position so the deserializer can read the whole file
    return DataType.for_string(first_char, file.name)


def _is_single_playlist(data) -> TypeGuard[PlaylistXmlDict]:
    if not isinstance(data, Mapping):
        return False
    return 2 <= len(data) <= 3 and isinstance(data.get('playlist'), str) and isinstance(data.get('tracks'), list)


def _is_name_playlist_map(data) -> TypeGuard[dict[str, PlaylistXmlDict]]:
    if not isinstance(data, Mapping):
        return False
    return all(isinstance(k, str) and _is_single_playlist(v) for k, v in data.items())
