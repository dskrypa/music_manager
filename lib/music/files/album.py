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
from ds_tools.fs.paths import iter_paths, Paths

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
    from music.text.name import Name
    from music.typing import PathLike, Strings, StrIter
    from .parsing import AlbumName
    from .track.patterns import StrsOrPatterns
    from .typing import ProgressCB

__all__ = ['AlbumDir', 'iter_album_dirs', 'iter_albums_or_files']
log = logging.getLogger(__name__)


class AlbumDir(Collection[SongFile], ClearableCachedPropertyMixin):
    __instances = {}
    path: Path

    def __new__(cls, path: PathLike):
        path = _normalize_init_path(path)
        try:
            return cls.__instances[path]
        except KeyError:
            pass
        if any(p.is_dir() for p in path.iterdir()):
            raise InvalidAlbumDir(f'Invalid album dir - contains directories: {path.as_posix()}')

        cls.__instances[path] = obj = super().__new__(cls)
        return obj

    def __init__(self, path: PathLike):
        """
        :param path: The path to a directory that contains one album's music files
        """
        path = _normalize_init_path(path)
        if any(p.is_dir() for p in path.iterdir()):
            raise InvalidAlbumDir(f'Invalid album dir - contains directories: {path.as_posix()}')
        self.path = path

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__}({self.relative_path!r})>'

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
            log.warning('Conflicting album titles were found for {}: {}'.format(self, ', '.join(map(str, titles))))
        elif not titles:
            log.warning('No album titles were found for {}'.format(self))
        return title

    @cached_property
    def all_artists(self) -> set[Name]:
        return set(chain.from_iterable(music_file.all_artists for music_file in self.songs))

    @cached_property
    def artist_url(self):
        urls = set(music_file.artist_url for music_file in self.songs)
        if len(urls) == 1:
            return next(iter(urls))
        elif urls:
            log.debug(f'Found too many ({len(urls)}) artist URLs for {self}')
        return None

    @cached_property
    def album_url(self):
        urls = set(music_file.album_url for music_file in self.songs)
        if len(urls) == 1:
            return next(iter(urls))
        elif urls:
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
                # noinspection PyUnboundLocalVariable
                groups[group].add(artist)
        return groups

    @cached_property
    def album_artist(self) -> Optional[Name]:
        if artists := self.album_artists:
            if len(artists) == 1:
                return next(iter(artists))

            artists = Counter(chain.from_iterable(music_file.album_artists for music_file in self.songs))
            artist = max(artists.items(), key=lambda kv: kv[1])[0]  # noqa
            return artist
        return None

    @cached_property
    def artist(self) -> Optional[Name]:
        if (artists := self.artists) and len(artists) == 1:
            return next(iter(artists))
        return None

    @cached_property
    def names(self) -> set[AlbumName]:
        return {music_file.album_name for music_file in self.songs}

    @cached_property
    def name(self) -> Optional[AlbumName]:
        if names := self.names:
            if len(names) == 1:
                return next(iter(names))

            names = Counter(music_file.album_name for music_file in self.songs)
            name = max(names.items(), key=lambda kv: kv[1])[0]  # noqa
            return name

        log.debug(f'{self}.names => {names}')
        return None

    @cached_property
    def type(self) -> DiscoEntryType:
        if name := self.name:
            return name.type
        return DiscoEntryType.UNKNOWN

    @property
    def length(self) -> int:
        """
        :return float: The length of this album in seconds
        """
        return sum(f.length for f in self.songs)

    @cached_property
    def length_str(self) -> str:
        """
        :return str: The length of this album in the format (HH:M)M:SS
        """
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
            log.error('Error determining disk number for {}: {}'.format(self, nums))
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
    for path in iter_paths(paths):
        if path.is_dir():
            for root, dirs, files in os.walk(path.as_posix()):  # as_posix for 3.5 compatibility
                if files and not dirs:
                    yield AlbumDir(root)
        elif path.is_file():
            yield AlbumDir(path.parent)


def iter_albums_or_files(paths: Paths) -> Iterator[Union[AlbumDir, SongFile]]:
    for path in iter_paths(paths):
        if path.is_dir():
            for root, dirs, files in os.walk(path.as_posix()):  # as_posix for 3.5 compatibility
                if files and not dirs:
                    yield AlbumDir(root)
        elif path.is_file():
            yield SongFile(path)


def _normalize_init_path(path: PathLike) -> Path:
    if not isinstance(path, Path):
        path = Path(path).expanduser().resolve()
    return path.parent if path.is_file() else path


if __name__ == '__main__':
    from .patches import apply_mutagen_patches

    apply_mutagen_patches()
