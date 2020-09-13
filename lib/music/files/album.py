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
from typing import Iterator, List, Union, Optional, Set, Dict

from mutagen.id3 import TDRC

from ds_tools.caching import ClearableCachedPropertyMixin
from ds_tools.core import iter_paths, FnMatcher, Paths, ReMatcher
from tz_aware_dt import format_duration
from ..common import DiscoEntryType
from ..text import Name
from .exceptions import *
from .track import SongFile, AlbumName
from .utils import iter_music_files, get_common_changes

__all__ = ['AlbumDir', 'RM_TAG_MATCHERS', 'iter_album_dirs', 'iter_albums_or_files']
log = logging.getLogger(__name__)

RM_TAG_MATCHERS = {
    'mp3': ReMatcher(('TXXX:?(?!WIKI:)', 'PRIV.*', 'WXXX.*', 'COMM.*', 'TCOP')).match,
    'mp4': FnMatcher(('*itunes*', '??ID', '?cmt', 'ownr', 'xid ', 'purd', 'desc', 'ldes', 'cprt')).match,
    'flac': FnMatcher(('UPLOAD*', 'WWW*', 'COMM*')).match
}
KEEP_TAGS = {'----:com.apple.iTunes:ISRC', '----:com.apple.iTunes:LANGUAGE'}
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
    def songs(self) -> List[SongFile]:
        songs = list(iter_music_files(self.path))
        for song in songs:
            song._in_album_dir = True
            song._album_dir = self
        return songs

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
    def all_artists(self) -> Set[Name]:
        return set(chain.from_iterable(music_file.all_artists for music_file in self.songs))

    @cached_property
    def album_artists(self) -> Set[Name]:
        return set(chain.from_iterable(music_file.album_artists for music_file in self.songs))

    @cached_property
    def artists(self) -> Set[Name]:
        return set(chain.from_iterable(music_file.artists for music_file in self.songs))

    @cached_property
    def _groups(self) -> Dict[str, Set[Name]]:
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
    def names(self) -> Set[AlbumName]:
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

    def fix_song_tags(self, dry_run=False, add_bpm=False):
        prefix, add_msg, rmv_msg = ('[DRY RUN] ', 'Would add', 'remove') if dry_run else ('', 'Adding', 'removing')

        for music_file in self.songs:
            music_file.cleanup_lyrics(dry_run)
            tag_type = music_file.tag_type
            if tag_type != 'mp3':
                log.debug(f'Skipping date tags for non-MP3: {music_file}')
                continue

            tdrc = music_file.tags.getall('TDRC')
            txxx_date = music_file.tags.getall('TXXX:DATE')
            if (not tdrc) and txxx_date:
                file_date = txxx_date[0].text[0]

                log.info(f'{prefix}{add_msg} TDRC={file_date} to {music_file} and {rmv_msg} its TXXX:DATE tag')
                if not dry_run:
                    music_file.tags.add(TDRC(text=file_date))
                    music_file.tags.delall('TXXX:DATE')
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

            for future in futures.as_completed({EXECUTOR.submit(bpm_func, music_file) for music_file in self.songs}):
                future.result()

    def remove_bad_tags(self, dry_run=False):
        i = 0
        for music_file in self.songs:
            try:
                rm_tag_match = RM_TAG_MATCHERS[music_file.tag_type]
            except KeyError as e:
                raise TypeError(f'Unhandled tag type: {music_file.tag_type}') from e

            if music_file.tag_type == 'flac':
                log.info(f'{music_file}: Bad tag removal is not currently supported for flac files')
                # noinspection PyArgumentList
                if to_remove := {tag for tag, val in music_file.tags if rm_tag_match(tag) and tag not in KEEP_TAGS}:
                    if i:
                        log.debug('')
            else:
                # noinspection PyArgumentList
                if to_remove := {tag for tag in music_file.tags if rm_tag_match(tag) and tag not in KEEP_TAGS}:
                    if i:
                        log.debug('')

            i += int(music_file.remove_tags(to_remove, dry_run))

        if not i:
            log.debug(f'None of the songs in {self} had any tags that needed to be removed')

    def update_tags_with_value(self, tag_ids, value, patterns=None, partial=False, dry_run=False):
        updates = {file: file.get_tag_updates(tag_ids, value, patterns=patterns, partial=partial) for file in self}
        if any(values for values in updates.values()):
            common_changes = get_common_changes(self, updates, dry_run=dry_run)
            for file, values in updates.items():
                file.update_tags(values, dry_run, no_log=common_changes, none_level=20)
        else:
            log.info(f'No changes to make for {self}')


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


@atexit.register
def _cleanup_executor():
    if EXECUTOR is not None:
        EXECUTOR.shutdown(True)


# Note: The only time this property is not available is in interactive sessions started for the files.track.base module
SongFile.album_dir_obj = cached_property(_album_dir_obj)


if __name__ == '__main__':
    from .patches import apply_mutagen_patches
    apply_mutagen_patches()
