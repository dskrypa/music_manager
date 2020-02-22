"""
:author: Doug Skrypa
"""

import logging
import os
import re
from fnmatch import fnmatch
from pathlib import Path

from mutagen.id3 import ID3, TDRC
from mutagen.mp4 import MP4Tags

from ds_tools.caching import ClearableCachedPropertyMixin
from ds_tools.compat import cached_property
from tz_aware_dt import format_duration
from .exceptions import *
from .patches import tag_repr
from .track import BaseSongFile
from .utils import _iter_music_files

__all__ = ['AlbumDir', 'RM_TAGS_MP4', 'RM_TAGS_ID3', 'iter_album_dirs']
log = logging.getLogger(__name__)

RM_TAGS_MP4 = ['*itunes*', '??ID', '?cmt', 'ownr', 'xid ', 'purd', 'desc', 'ldes', 'cprt']
RM_TAGS_ID3 = ['TXXX*', 'PRIV*', 'WXXX*', 'COMM*', 'TCOP']


class AlbumDir(ClearableCachedPropertyMixin):
    __instances = {}

    def __new__(cls, path):
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

    def __init__(self, path):
        """
        :param str|Path path: The path to a directory that contains one album's music files
        """
        if not isinstance(path, Path):
            path = Path(path).expanduser().resolve()
        if any(p.is_dir() for p in path.iterdir()):
            raise InvalidAlbumDir('Invalid album dir - contains directories: {}'.format(path.as_posix()))
        self.path = path
        self._album_score = -1

    def __repr__(self):
        try:
            rel_path = self.path.relative_to(Path('.').resolve()).as_posix()
        except Exception as e:
            rel_path = self.path.as_posix()
        return '<{}({!r})>'.format(type(self).__name__, rel_path)

    def __iter__(self):
        yield from self.songs

    def __len__(self):
        return len(self.songs)

    def move(self, dest_path):
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
    def songs(self):
        songs = list(_iter_music_files(self.path.as_posix()))
        for song in songs:
            song._in_album_dir = True
            song._album_dir = self
        return songs

    @cached_property
    def name(self):
        album = self.path.name
        m = re.match('^\[\d{4}[0-9.]*\] (.*)$', album)  # Begins with date
        if m:
            album = m.group(1).strip()
        m = re.match('(.*)\s*\[.*Album\]', album)  # Ends with Xth Album
        if m:
            album = m.group(1).strip()
        return album

    @cached_property
    def artist_path(self):
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
    def _type_path(self):
        """Not accurate if not already sorted"""
        return self.path.parent

    @property
    def length(self):
        """
        :return float: The length of this album in seconds
        """
        return sum(f.length for f in self.songs)

    @cached_property
    def length_str(self):
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
    def _is_full_ost(self):
        return all(f._is_full_ost for f in self.songs)

    @cached_property
    def title(self):
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
    def disk_num(self):
        nums = {f.disk_num for f in self.songs}
        if len(nums) == 1:
            return nums.pop()
        else:
            log.error('Error determining disk number for {}: {}'.format(self, nums))
            return None

    @cached_property
    def tag_release_date(self):
        try:
            dates = {f.date for f in self.songs}
        except Exception as e:
            pass
        else:
            if len(dates) == 1:
                return dates.pop()
        return None

    def fix_song_tags(self, dry_run):
        prefix, add_msg, rmv_msg = ('[DRY RUN] ', 'Would add', 'remove') if dry_run else ('', 'Adding', 'removing')
        upd_msg = 'Would update' if dry_run else 'Updating'

        for music_file in self.songs:
            if music_file.ext != 'mp3':
                log.debug('Skipping non-MP3: {}'.format(music_file))
                continue

            tdrc = music_file.tags.getall('TDRC')
            txxx_date = music_file.tags.getall('TXXX:DATE')
            if (not tdrc) and txxx_date:
                file_date = txxx_date[0].text[0]

                log.info('{}{} TDRC={} to {} and {} its TXXX:DATE tag'.format(
                    prefix, add_msg, file_date, music_file, rmv_msg
                ))
                if not dry_run:
                    music_file.tags.add(TDRC(text=file_date))
                    music_file.tags.delall('TXXX:DATE')
                    music_file.save()

            changes = 0
            for uslt in music_file.tags.getall('USLT'):
                m = re.match(r'^(.*)(https?://\S+)$', uslt.text, re.DOTALL)
                if m:
                    # noinspection PyUnresolvedReferences
                    new_lyrics = m.group(1).strip() + '\r\n'
                    log.info('{}{} lyrics for {} from {!r} to {!r}'.format(
                        prefix, upd_msg, music_file, tag_repr(uslt.text), tag_repr(new_lyrics)
                    ))
                    if not dry_run:
                        uslt.text = new_lyrics
                        changes += 1

            if changes and not dry_run:
                log.info('Saving changes to lyrics in {}'.format(music_file))
                music_file.save()

    def remove_bad_tags(self, dry_run):
        prefix = '[DRY RUN] Would remove' if dry_run else 'Removing'
        i = 0
        for music_file in self.songs:
            if isinstance(music_file.tags, MP4Tags):
                tag_id_pats = RM_TAGS_MP4
            elif isinstance(music_file.tags, ID3):
                tag_id_pats = RM_TAGS_ID3
            else:
                raise TypeError('Unhandled tag type: {}'.format(type(music_file.tags).__name__))

            to_remove = {}
            for tag, val in sorted(music_file.tags.items()):
                if any(fnmatch(tag, pat) for pat in tag_id_pats):
                    to_remove[tag] = val if isinstance(val, list) else [val]

            if to_remove:
                if i:
                    log.debug('')
                rm_str = ', '.join(
                    '{}: {}'.format(tag_id, tag_repr(val)) for tag_id, vals in sorted(to_remove.items()) for val in vals
                )
                info_str = ', '.join('{} ({})'.format(tag_id, len(vals)) for tag_id, vals in sorted(to_remove.items()))

                log.info('{} tags from {}: {}'.format(prefix, music_file, info_str))
                log.debug('\t{}: {}'.format(music_file.filename, rm_str))
                if not dry_run:
                    for tag_id in to_remove:
                        if isinstance(music_file.tags, MP4Tags):
                            del music_file.tags[tag_id]
                        elif isinstance(music_file.tags, ID3):
                            music_file.tags.delall(tag_id)
                    music_file.save()
                i += 1
            else:
                log.debug('{}: Did not have the tags specified for removal'.format(music_file.filename))

        if not i:
            log.debug('None of the songs in {} had any tags that needed to be removed'.format(self))


def iter_album_dirs(paths):
    if isinstance(paths, str):
        paths = [paths]

    for _path in paths:
        path = Path(_path).expanduser().resolve()
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
