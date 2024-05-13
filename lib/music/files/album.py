"""
:author: Doug Skrypa
"""

from __future__ import annotations

import logging
import os
from collections import defaultdict, Counter
from itertools import chain
from pathlib import Path
from typing import TYPE_CHECKING, Iterator, Union, Optional, Collection

from ds_tools.caching.decorators import ClearableCachedPropertyMixin, cached_property
from ds_tools.fs.paths import iter_paths

from music.common.disco_entry import DiscoEntryType
from music.common.utils import format_duration
from .bulk_actions import remove_bad_tags, fix_song_tags
from .changes import get_common_changes
from .cover import prepare_cover_image
from .exceptions import InvalidAlbumDir
from .track.track import SongFile, iter_music_files

if TYPE_CHECKING:
    from datetime import date
    from PIL.Image import Image as PILImage
    from watchdog.events import FileSystemEvent
    from watchdog.observers import Observer
    from music.text.name import Name
    from music.typing import PathLike, Strings, StrIter
    from ds_tools.fs.typing import Paths
    from .parsing import AlbumName
    from .track.patterns import StrsOrPatterns
    from .typing import ProgressCB

__all__ = ['MultiAlbumDir', 'AlbumDir', 'iter_album_dirs', 'iter_albums_or_files']
log = logging.getLogger(__name__)


class MultiAlbumDir(ClearableCachedPropertyMixin):
    def __init__(self, path: Path):
        if not path.is_dir():
            raise TypeError(f'Invalid multi-album dir={path.as_posix()!r} - not a directory')
        self.path = path
        if (observer := self.observer) is not None:
            log.debug(f'Configuring watchdog observer for {self.path.as_posix()}')
            observer.schedule(self, self.path.as_posix())
            observer.start()

    @cached_property
    def _album_paths(self) -> list[Path]:
        album_paths = [p for p in self.path.iterdir() if p.is_dir() and not any(sp.is_dir() for sp in p.iterdir())]
        album_paths.sort(key=lambda p: p.name.lower())
        return album_paths

    @cached_property
    def _album_dirs(self) -> set[AlbumDir]:
        return set()

    # region Container Methods

    def __len__(self) -> int:
        return len(self._album_paths)

    def __getitem__(self, item: int) -> AlbumDir:
        return AlbumDir(self._album_paths[item])

    def __iter__(self) -> Iterator[AlbumDir]:
        for path in self._album_paths:
            yield AlbumDir(path)

    # endregion

    # region Index Methods

    def index(self, album: AlbumDir | PathLike) -> int:
        path = album.path if isinstance(album, AlbumDir) else _normalize_init_path(album)
        return self._album_paths.index(path)

    def get_prev_index(self, album: AlbumDir | PathLike) -> int | None:
        try:
            index = self.index(album) - 1
        except IndexError:
            return None
        return None if index < 0 else index

    def get_next_index(self, album: AlbumDir | PathLike) -> int | None:
        try:
            index = self.index(album) + 1
        except IndexError:
            return None
        return None if index >= len(self._album_paths) else index

    # endregion

    # region File Watch Methods

    @cached_property
    def observer(self) -> Observer | None:
        try:
            from watchdog.observers import Observer
        except ImportError:
            return None
        return Observer()

    def dispatch(self, event: FileSystemEvent):
        if event.is_directory or event.event_type == 'deleted':  # It registers dir moves out / dir deletion as non-dir
            log.debug(f'Resetting cached properties due to {event=} for {self.path.as_posix()}')
            for album_dir in self._album_dirs:
                album_dir.clear_cached_properties(
                    'parent', 'prev_sibling', 'next_sibling', 'has_prev_sibling', 'has_next_sibling'
                )
            self.clear_cached_properties('_album_paths', '_album_dirs')
        # else:
        #     log.debug(f'Ignoring {event=}')

    def close(self):
        if (observer := self.observer) is not None:
            log.debug(f'Stopping {observer=} for {self.path.as_posix()}')
            observer.stop()
            observer.join()

    def __del__(self):
        self.close()

    # endregion


class AlbumDir(Collection[SongFile], ClearableCachedPropertyMixin):
    __instances = {}

    path: Path

    def __new__(cls, path: PathLike):
        path = _normalize_init_path(path)
        try:
            return cls.__instances[path]
        except KeyError:
            pass

        try:
            contains_dirs = any(p.is_dir() for p in path.iterdir())
        except FileNotFoundError as e:
            raise InvalidAlbumDir(f"Invalid album dir - doesn't exist: {path.as_posix()}") from e
        if contains_dirs:
            raise InvalidAlbumDir(f'Invalid album dir - contains directories: {path.as_posix()}')

        cls.__instances[path] = obj = super().__new__(cls)
        obj.path = path
        return obj

    def __init__(self, path: PathLike):
        """
        :param path: The path to a directory that contains one album's music files
        """
        if not hasattr(self, 'path'):
            self.path = path  # This would never really happen

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__}({self.relative_path!r})>'

    # region Parent / Sibling Album Directories

    @cached_property
    def parent(self) -> MultiAlbumDir:
        parent = MultiAlbumDir(self.path.parent)
        parent._album_dirs.add(self)
        return parent

    @cached_property
    def prev_sibling(self) -> AlbumDir | None:
        if (index := self.parent.get_prev_index(self.path)) is not None:
            return self.parent[index]
        return None

    @cached_property
    def next_sibling(self) -> AlbumDir | None:
        if (index := self.parent.get_next_index(self.path)) is not None:
            return self.parent[index]
        return None

    @cached_property
    def has_prev_sibling(self) -> bool:
        return self.prev_sibling is not None

    @cached_property
    def has_next_sibling(self) -> bool:
        return self.next_sibling is not None

    # endregion

    # region Tracks / Container Methods

    def __iter__(self) -> Iterator[SongFile]:
        return iter(self.songs)

    def __len__(self) -> int:
        return len(self.songs)

    def __getitem__(self, path: PathLike) -> SongFile:
        if isinstance(path, str):
            path = Path(path).expanduser()
        try:
            return self.path_track_map[path]
        except KeyError:
            pass
        path = path.resolve()
        return self.path_track_map[path]

    def __contains__(self, item: PathLike | SongFile) -> bool:  # noqa  # Pycharm doesn't like the specific annotation
        if isinstance(item, SongFile):
            return item in self.songs
        try:
            self[item]
        except KeyError:
            return False
        else:
            return True

    @cached_property
    def songs(self) -> list[SongFile]:
        songs = list(iter_music_files(self.path))
        for song in songs:
            song._in_album_dir = True
            song._album_dir = self
        try:
            songs.sort(key=lambda t: (t.disk_num, t.track_num))
        except Exception as e:
            log.debug(f'Error sorting tracks in {self}: {e}', exc_info=True)
        return songs

    @cached_property
    def path_track_map(self) -> dict[Path, SongFile]:
        return {track.path: track for track in self.songs}

    # endregion

    def refresh(self):
        for track in self.songs:
            track.clear_cached_properties()
        self.clear_cached_properties()

    @property
    def relative_path(self) -> str:
        try:
            return self.path.relative_to(Path.cwd().resolve()).as_posix()
        except Exception:  # noqa
            return self.path.as_posix()

    def move(self, dest_path: PathLike):
        if not isinstance(dest_path, Path):
            dest_path = Path(dest_path)
        dest_path = dest_path.expanduser().resolve()

        if not dest_path.parent.exists():
            dest_path.parent.mkdir(parents=True)
        if dest_path.exists():
            raise ValueError(f'Destination for {self} already exists: {dest_path}')

        del self.__class__.__instances[self.path]
        self.path.rename(dest_path)
        self.path = dest_path
        self.__class__.__instances[self.path] = self
        self.clear_cached_properties()

    # region Tag-based Properties

    @cached_property
    def title(self) -> Optional[str]:
        titles = {f.album_name_cleaned_plus_and_part[0] for f in self.songs}
        title = None
        if len(titles) == 1:
            title = titles.pop()
        elif len(titles) > 1:
            log.warning(f'Conflicting album titles were found for {self}: {", ".join(map(str, titles))}')
        elif not titles:
            log.warning(f'No album titles were found for {self}')
        return title

    @cached_property
    def all_artists(self) -> set[Name]:
        return set(chain.from_iterable(music_file.all_artists for music_file in self.songs))

    @cached_property
    def artist_url(self) -> str | None:
        if urls := set(music_file.artist_url for music_file in self.songs):
            if len(urls) == 1:
                return next(iter(urls))
            log.debug(f'Found too many ({len(urls)}) artist URLs for {self}')
        return None

    @cached_property
    def album_url(self) -> str | None:
        if urls := set(music_file.album_url for music_file in self.songs):
            if len(urls) == 1:
                return next(iter(urls))
            log.debug(f'Found too many ({len(urls)}) album URLs for {self}')
        return None

    @cached_property
    def album_artists(self) -> set[Name]:
        return set(chain.from_iterable(music_file.album_artists for music_file in self.songs))

    @cached_property
    def artists(self) -> set[Name]:
        return set(chain.from_iterable(music_file.artists for music_file in self.songs))

    @cached_property
    def _groups(self) -> dict[str, set[Name]]:
        groups = defaultdict(set)
        for artist in self.all_artists:
            if (extra := artist.extra) and (group := extra.get('group')):
                groups[group].add(artist)
        return groups

    @cached_property
    def album_artist(self) -> Optional[Name]:
        if artists := self.album_artists:
            if len(artists) == 1:
                return next(iter(artists))

            artists = Counter(a for music_file in self.songs for a in music_file.album_artists)
            return max(artists.items(), key=lambda kv: kv[1])[0]

        return None

    @cached_property
    def artist(self) -> Optional[Name]:
        if (artists := self.artists) and len(artists) == 1:
            return next(iter(artists))
        return None

    @cached_property
    def names(self) -> set[AlbumName]:
        if names := set(self._album_names_from_tracks()):
            return names

        # If there is only one track, or two with matching names where one is an instrumental version, assume this
        # album is a single
        if len(self.songs) == 1 and (name := self.songs[0].title_as_album_name):
            return {name}
        elif len(self.songs) == 2:
            ts = sorted([(s.tag_title, s) for s in self.songs], key=lambda x: len(x[0]))
            if ts[1][0].startswith(ts[0][0]) and '(inst' in ts[1][0] and (name := ts[0][1].title_as_album_name):
                return {name}

        return names

    @cached_property
    def name(self) -> Optional[AlbumName]:
        if names := self.names:
            if len(names) == 1:
                return next(iter(names))

            # names = Counter(music_file.album_name for music_file in self.songs)
            # return max(names.items(), key=lambda kv: kv[1])[0]
            names = Counter(self._album_names_from_tracks())
            max_count = max(names.values())
            # Pick the alphanumerically sorted first name that occurs most frequently, even if multiple names have
            # the name number of occurrences
            return min(name for name, freq in names.items() if freq == max_count)

        log.debug(f'{self}.names => {names}')
        return None

    def _album_names_from_tracks(self) -> Iterator[AlbumName]:
        for track in self.songs:
            if track.album_name:
                yield track.album_name
            if track.album_title_name:
                yield track.album_title_name

    @cached_property
    def type(self) -> DiscoEntryType:
        return self.name.type if self.name else DiscoEntryType.UNKNOWN

    @property
    def length(self) -> float:
        """The length of this album in seconds"""
        return sum(f.length for f in self.songs)

    @cached_property
    def length_str(self) -> str:
        """The length of this album in the format (HH:M)M:SS"""
        length = format_duration(int(self.length))  # Most other programs seem to floor the seconds
        if length.startswith('00:'):
            length = length[3:]
        if length.startswith('0'):
            length = length[1:]
        return length

    @cached_property
    def disk_num(self) -> Optional[int]:
        nums = {f.disk_num for f in self.songs}
        if len(nums) == 1:
            return nums.pop()
        else:
            log.error(f'Error determining disk number for {self}: {nums}')
            return None

    @cached_property
    def date(self) -> Optional[date]:
        try:
            dates = {f.date for f in self.songs}
        except Exception as e:
            log.debug(f'Error processing date for {self}: {e}')
        else:
            if len(dates) == 1:
                return dates.pop()
            elif len(dates) > 1:
                log.debug('Multiple dates found in {}: {}'.format(self, ', '.join(sorted(map(str, dates)))))
        return None

    # endregion

    def fix_song_tags(self, dry_run: bool = False, add_bpm: bool = False, cb: ProgressCB = None):
        fix_song_tags(self.songs, dry_run=dry_run, add_bpm=add_bpm, cb=cb)

    def remove_bad_tags(self, dry_run: bool = False, cb: ProgressCB = None, extras: Strings = None):
        remove_bad_tags(self, dry_run=dry_run, cb=cb, extras=extras)

    def update_tags_with_value(
        self,
        tag_ids: StrIter,
        value: str,
        patterns: StrsOrPatterns = None,
        partial: bool = False,
        dry_run: bool = False,
    ):
        updates = {file: file.get_tag_updates(tag_ids, value, patterns=patterns, partial=partial) for file in self}
        if any(values for values in updates.values()):
            common_changes = get_common_changes(self, updates, dry_run=dry_run)
            for file, values in updates.items():
                file.update_tags(values, dry_run, no_log=common_changes, none_level=20)
        else:
            log.info(f'No changes to make for {self}')

    @cached_property
    def has_any_cover(self) -> bool:
        for song_file in self.songs:
            try:
                data, ext = song_file.get_cover_data()
            except Exception:  # noqa
                pass
            else:
                if data:
                    return True
        return False

    def set_cover_data(self, image: PILImage, dry_run: bool = False, max_width: int = 1200):
        image, data, mime_type = prepare_cover_image(image, {f.tag_type for f in self.songs}, max_width)
        for song_file in self.songs:
            song_file._set_cover_data(image, data, mime_type, dry_run)


def iter_album_dirs(paths: Paths) -> Iterator[AlbumDir]:
    return _iter_albums_or_files(paths, False)


def iter_albums_or_files(paths: Paths) -> Iterator[Union[AlbumDir, SongFile]]:
    return _iter_albums_or_files(paths, True)


def _iter_albums_or_files(paths: Paths, allow_files: bool) -> Iterator[Union[AlbumDir, SongFile]]:
    for path in iter_paths(paths):
        if path.is_dir():
            for root, dirs, files in os.walk(path):
                if files and not dirs:
                    yield AlbumDir(root)
        elif path.is_file():
            yield SongFile(path) if allow_files else AlbumDir(path.parent)


def _normalize_init_path(path: PathLike) -> Path:
    if not isinstance(path, Path):
        path = Path(path).expanduser().resolve()
    return path.parent if path.is_file() else path


if __name__ == '__main__':
    from .patches import apply_mutagen_patches

    apply_mutagen_patches()
