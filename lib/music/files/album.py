"""
:author: Doug Skrypa
"""

import atexit
import logging
import os
from collections import defaultdict, Counter
from concurrent import futures
from datetime import date
from functools import cached_property
from itertools import chain
from pathlib import Path
from typing import TYPE_CHECKING, Iterator, Union, Optional, Callable, Iterable, Collection

from mutagen.id3 import TDRC, ID3

from ds_tools.caching.mixins import ClearableCachedPropertyMixin
from ds_tools.core.patterns import FnMatcher, ReMatcher
from ds_tools.fs.paths import iter_paths, Paths
from tz_aware_dt import format_duration
from ..common.disco_entry import DiscoEntryType
from ..text.name import Name
from .changes import get_common_changes
from .cover import prepare_cover_image
from .exceptions import InvalidAlbumDir
from .parsing import AlbumName
from .track.track import SongFile, iter_music_files

if TYPE_CHECKING:
    from PIL import Image

__all__ = ['AlbumDir', 'iter_album_dirs', 'iter_albums_or_files']
log = logging.getLogger(__name__)
EXECUTOR = None     # type: Optional[futures.ThreadPoolExecutor]


class AlbumDir(ClearableCachedPropertyMixin):
    __instances = {}

    def __new__(cls, path: Union[Path, str]):
        if not isinstance(path, Path):
            path = Path(path).expanduser().resolve()

        if path not in cls.__instances:
            if any(p.is_dir() for p in path.iterdir()):
                raise InvalidAlbumDir(f'Invalid album dir - contains directories: {path.as_posix()}')

            obj = super().__new__(cls)
            cls.__instances[path] = obj
            return obj
        else:
            return cls.__instances[path]

    def __init__(self, path: Union[Path, str]):
        """
        :param str|Path path: The path to a directory that contains one album's music files
        """
        if not isinstance(path, Path):
            path = Path(path).expanduser().resolve()
        if any(p.is_dir() for p in path.iterdir()):
            raise InvalidAlbumDir('Invalid album dir - contains directories: {}'.format(path.as_posix()))
        self.path = path
        self._album_score = -1

    def __repr__(self) -> str:
        try:
            rel_path = self.path.relative_to(Path('.').resolve()).as_posix()
        except Exception:
            rel_path = self.path.as_posix()
        return '<{}({!r})>'.format(type(self).__name__, rel_path)

    def __iter__(self) -> Iterator[SongFile]:
        return iter(self.songs)

    def __len__(self) -> int:
        return len(self.songs)

    def __getitem__(self, path: Union[str, Path]) -> SongFile:
        if isinstance(path, str):
            path = Path(path).expanduser()
        try:
            return self.path_track_map[path]
        except KeyError:
            pass
        path = path.resolve()
        return self.path_track_map[path]

    def move(self, dest_path: Union[Path, str]):
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
            artist = max(artists.items(), key=lambda kv: kv[1])[0]
            return artist
        return None

    @cached_property
    def artist(self) -> Optional[Name]:
        if (artists := self.artists) and len(artists) == 1:
            return next(iter(artists))
        return None

    @cached_property
    def names(self) -> set[AlbumName]:
        return {music_file.album for music_file in self.songs}

    @cached_property
    def name(self) -> Optional[AlbumName]:
        if names := self.names:
            if len(names) == 1:
                return next(iter(names))

            names = Counter(music_file.album for music_file in self.songs)
            name = max(names.items(), key=lambda kv: kv[1])[0]
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

    def fix_song_tags(self, dry_run: bool = False, add_bpm: bool = False, callback: Callable = None):
        self._fix_song_tags(self.songs, dry_run=dry_run, add_bpm=add_bpm, callback=callback)

    @classmethod
    def _fix_song_tags(
        cls, tracks: Iterable[SongFile], dry_run: bool = False, add_bpm: bool = False, callback: Callable = None
    ):
        prefix, add_msg, rmv_msg = ('[DRY RUN] ', 'Would add', 'remove') if dry_run else ('', 'Adding', 'removing')
        for n, music_file in enumerate(tracks, 1):
            if callback:
                callback(music_file, n)
            music_file.cleanup_lyrics(dry_run)
            tag_type = music_file.tag_type
            if tag_type != 'id3':
                log.debug(f'Skipping tag fix for non-MP3: {music_file}')
                continue
            elif not isinstance((track_tags := music_file.tags), ID3):
                log.debug(f'Skipping tag fix due to no tags present in {music_file}')
                continue

            tdrc = track_tags.getall('TDRC')
            txxx_date = track_tags.getall('TXXX:DATE')
            if (not tdrc) and txxx_date:
                file_date = txxx_date[0].text[0]

                log.info(f'{prefix}{add_msg} TDRC={file_date} to {music_file} and {rmv_msg} its TXXX:DATE tag')
                if not dry_run:
                    track_tags.add(TDRC(text=file_date))
                    track_tags.delall('TXXX:DATE')
                    music_file.save()

        if add_bpm:
            def bpm_func(_file):
                bpm = _file.bpm(False, False)
                if bpm is None:
                    bpm = _file.bpm(not dry_run, calculate=True)
                    log.info(f'{prefix}{add_msg} BPM={bpm} to {_file}')

            global EXECUTOR
            if EXECUTOR is None:
                EXECUTOR = futures.ThreadPoolExecutor(max_workers=8)
                atexit.register(EXECUTOR.shutdown)

            for future in futures.as_completed({EXECUTOR.submit(bpm_func, music_file) for music_file in tracks}):
                future.result()

    def remove_bad_tags(self, dry_run: bool = False, callback: Callable = None, extras: Collection[str] = None):
        self._remove_bad_tags(self, dry_run, callback, extras)

    @classmethod
    def _remove_bad_tags(
        cls,
        tracks: Iterable[SongFile],
        dry_run: bool = False,
        callback: Callable = None,
        extras: Collection[str] = None,
    ):
        keep_tags = {'----:com.apple.iTunes:ISRC', '----:com.apple.iTunes:LANGUAGE'}
        i = 0
        for n, music_file in enumerate(tracks, 1):
            if callback:
                callback(music_file, n)
            try:
                rm_tag_match = _rm_tag_matcher(music_file.tag_type, extras)
            except TypeError as e:
                raise TypeError(f'Unhandled tag type={music_file.tag_type!r} for {music_file=}') from e
            if (track_tags := music_file.tags) is not None:
                if music_file.tag_type == 'vorbis':
                    # noinspection PyArgumentList
                    if to_remove := {tag for tag, val in track_tags if rm_tag_match(tag) and tag not in keep_tags}:
                        if i:
                            log.debug('')
                else:
                    # noinspection PyArgumentList
                    if to_remove := {tag for tag in track_tags if rm_tag_match(tag) and tag not in keep_tags}:
                        if i:
                            log.debug('')

                i += int(music_file.remove_tags(to_remove, dry_run))

        if not i:
            mid = f'songs in {tracks}' if isinstance(tracks, cls) else 'provided songs'
            log.debug(f'None of the {mid} had any tags that needed to be removed')

    def update_tags_with_value(self, tag_ids, value, patterns=None, partial=False, dry_run=False):
        updates = {file: file.get_tag_updates(tag_ids, value, patterns=patterns, partial=partial) for file in self}
        if any(values for values in updates.values()):
            common_changes = get_common_changes(self, updates, dry_run=dry_run)
            for file, values in updates.items():
                file.update_tags(values, dry_run, no_log=common_changes, none_level=20)
        else:
            log.info(f'No changes to make for {self}')

    def _prepare_cover_image(self, image: 'Image.Image', max_width: int = 1200) -> tuple['Image.Image', bytes, str]:
        return prepare_cover_image(image, {f.tag_type for f in self.songs}, max_width)

    def set_cover_data(self, image: 'Image.Image', dry_run: bool = False, max_width: int = 1200):
        image, data, mime_type = self._prepare_cover_image(image, max_width)
        for song_file in self.songs:
            song_file._set_cover_data(image, data, mime_type, dry_run)


def _rm_tag_matcher(tag_type: str, extras: Collection[str] = None) -> Callable:
    try:
        matchers = _rm_tag_matcher._matchers
    except AttributeError:
        matchers = _rm_tag_matcher._matchers = {
            'id3': ReMatcher(('TXXX(?::|$)(?!KPOP:GEN)', 'PRIV.*', 'WXXX(?::|$)(?!WIKI:A)', 'COMM.*', 'TCOP')).match,
            'mp4': FnMatcher(('*itunes*', '??ID', '?cmt', 'ownr', 'xid ', 'purd', 'desc', 'ldes', 'cprt')).match,
            'vorbis': FnMatcher(('UPLOAD*', 'WWW*', 'COMM*', 'UPC', 'TRACKTOTAL')).match
        }
    try:
        matcher = matchers[tag_type]
    except KeyError as e:
        raise TypeError(f'Unhandled tag type: {tag_type}') from e
    else:
        if extras:
            extras = set(map(str.lower, extras))

            def _matcher(value):
                if matcher(value):  # noqa
                    return True
                return value.lower() in extras

            return _matcher
        else:
            return matcher


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


def _album_dir_obj(self):
    if self._album_dir is not None:
        return self._album_dir
    try:
        return AlbumDir(self.path.parent)
    except InvalidAlbumDir:
        pass
    return None


# Note: The only time this property is not available is in interactive sessions started for the files.track.base module
SongFile.album_dir_obj = cached_property(_album_dir_obj)


if __name__ == '__main__':
    from .patches import apply_mutagen_patches
    apply_mutagen_patches()
