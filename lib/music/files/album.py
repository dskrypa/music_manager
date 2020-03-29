"""
:author: Doug Skrypa
"""

import logging
import os
import re
from datetime import date
from pathlib import Path
from typing import Iterator, List, Union, Optional

from mutagen.id3 import TDRC

from ds_tools.caching import ClearableCachedPropertyMixin
from ds_tools.compat import cached_property
from ds_tools.core import iter_paths, FnMatcher, Paths
from tz_aware_dt import format_duration
from .exceptions import *
from .track import BaseSongFile, SongFile, tag_repr
from .utils import iter_music_files

__all__ = ['AlbumDir', 'RM_TAG_MATCHERS', 'iter_album_dirs']
log = logging.getLogger(__name__)

RM_TAG_MATCHERS = {
    'mp3': FnMatcher(('TXXX*', 'PRIV*', 'WXXX*', 'COMM*', 'TCOP')).match,
    'mp4': FnMatcher(('*itunes*', '??ID', '?cmt', 'ownr', 'xid ', 'purd', 'desc', 'ldes', 'cprt')).match
}
KEEP_TAGS = {'----:com.apple.iTunes:ISRC', '----:com.apple.iTunes:LANGUAGE'}


class AlbumDir(ClearableCachedPropertyMixin):
    __instances = {}

    def __new__(cls, path: Union[Path, str]):
        if not isinstance(path, Path):
            path = Path(path).expanduser().resolve()

        str_path = path.as_posix()
        if str_path not in cls.__instances:
            if any(p.is_dir() for p in path.iterdir()):
                raise InvalidAlbumDir('Invalid album dir - contains directories: {}'.format(path.as_posix()))

            obj = super().__new__(cls)
            cls.__instances[str_path] = obj
            return obj
        else:
            return cls.__instances[str_path]

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
        except Exception as e:
            rel_path = self.path.as_posix()
        return '<{}({!r})>'.format(type(self).__name__, rel_path)

    def __iter__(self) -> Iterator[SongFile]:
        yield from self.songs

    def __len__(self) -> int:
        return len(self.songs)

    def move(self, dest_path: Union[Path, str]):
        if not isinstance(dest_path, Path):
            dest_path = Path(dest_path)
        dest_path = dest_path.expanduser().resolve()

        if not dest_path.parent.exists():
            os.makedirs(dest_path.parent.as_posix())
        if dest_path.exists():
            raise ValueError('Destination for {} already exists: {!r}'.format(self, dest_path.as_posix()))

        self.path.rename(dest_path)
        self.path = dest_path
        self.clear_cached_properties()

    @cached_property
    def songs(self) -> List[SongFile]:
        songs = list(iter_music_files(self.path))
        for song in songs:
            song._in_album_dir = True
            song._album_dir = self
        return songs

    @cached_property
    def name(self) -> str:
        album = self.path.name
        m = re.match('^\[\d{4}[0-9.]*\] (.*)$', album)  # Begins with date
        if m:
            album = m.group(1).strip()
        m = re.match('(.*)\s*\[.*Album\]', album)  # Ends with Xth Album
        if m:
            album = m.group(1).strip()
        return album

    @cached_property
    def artist_path(self) -> Optional[Path]:
        bad = (
            'album', 'single', 'soundtrack', 'collaboration', 'solo', 'christmas', 'download', 'compilation',
            'unknown_fixme'
        )
        artist_path = self.path.parent
        lc_name = artist_path.name.lower()
        if not any(i in lc_name for i in bad):
            return artist_path

        artist_path = artist_path.parent
        lc_name = artist_path.name.lower()
        if not any(i in lc_name for i in bad):
            return artist_path
        log.error('Unable to determine artist path for {}'.format(self))
        return None

    @cached_property
    def _type_path(self) -> Optional[Path]:
        """Not accurate if not already sorted"""
        return self.path.parent

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
    def _is_full_ost(self) -> bool:
        return all(f._is_full_ost for f in self.songs)

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
    def disk_num(self) -> Optional[int]:
        nums = {f.disk_num for f in self.songs}
        if len(nums) == 1:
            return nums.pop()
        else:
            log.error('Error determining disk number for {}: {}'.format(self, nums))
            return None

    @cached_property
    def tag_release_date(self) -> Optional[date]:
        try:
            dates = {f.date for f in self.songs}
        except Exception as e:
            pass
        else:
            if len(dates) == 1:
                return dates.pop()
        return None

    def fix_song_tags(self, dry_run=False, add_bpm=False):
        prefix, add_msg, rmv_msg = ('[DRY RUN] ', 'Would add', 'remove') if dry_run else ('', 'Adding', 'removing')

        for music_file in self.songs:
            music_file._cleanup_lyrics(dry_run)
            tag_type = music_file.tag_type
            if add_bpm:
                bpm = music_file.bpm(False, False)
                if bpm is None:
                    bpm = music_file.bpm(not dry_run, calculate=True)
                    log.info(f'{prefix}{add_msg} BPM={bpm} to {music_file}')

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

    def remove_bad_tags(self, dry_run=False):
        prefix = '[DRY RUN] Would remove' if dry_run else 'Removing'
        i = 0
        for music_file in self.songs:
            try:
                rm_tag_match = RM_TAG_MATCHERS[music_file.tag_type]
            except KeyError as e:
                raise TypeError(f'Unhandled tag type: {music_file.tag_type}') from e

            to_remove = {
                tag: val if isinstance(val, list) else [val]
                for tag, val in sorted(music_file.tags.items()) if rm_tag_match(tag) and tag not in KEEP_TAGS
            }
            if to_remove:
                if i:
                    log.debug('')
                rm_str = ', '.join(
                    f'{tag_id}: {tag_repr(val)}' for tag_id, vals in sorted(to_remove.items()) for val in vals
                )
                info_str = ', '.join(f'{tag_id} ({len(vals)})' for tag_id, vals in sorted(to_remove.items()))

                log.info(f'{prefix} tags from {music_file}: {info_str}')
                log.debug(f'\t{music_file.filename}: {rm_str}')
                if not dry_run:
                    for tag_id in to_remove:
                        music_file.delete_tag(tag_id)
                    music_file.save()
                i += 1
            else:
                log.debug('{}: Did not have the tags specified for removal'.format(music_file.filename))

        if not i:
            log.debug('None of the songs in {} had any tags that needed to be removed'.format(self))


def iter_album_dirs(paths: Paths) -> Iterator[AlbumDir]:
    for path in iter_paths(paths):
        if path.is_dir():
            for root, dirs, files in os.walk(path.as_posix()):  # as_posix for 3.5 compatibility
                if files and not dirs:
                    yield AlbumDir(root)
        elif path.is_file():
            yield AlbumDir(path.parent)


def _album_dir_obj(self):
    if self._album_dir is not None:
        return self._album_dir
    try:
        return AlbumDir(self.path.parent)
    except InvalidAlbumDir:
        pass
    return None


# Note: The only time this property is not available is in interactive sessions started for the files.track.base module
BaseSongFile.album_dir_obj = cached_property(_album_dir_obj)


if __name__ == '__main__':
    from .patches import apply_mutagen_patches
    apply_mutagen_patches()
