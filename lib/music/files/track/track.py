"""
:author: Doug Skrypa
"""

import logging
import os
from datetime import date
from tempfile import TemporaryDirectory
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from typing import Optional, Union, Iterator, Tuple, Set, Any, Iterable, Dict

import mutagen
import mutagen.id3._frames
from mutagen import File
from mutagen.flac import VCFLACDict
from mutagen.id3 import ID3, POPM, Frames
from mutagen.mp4 import MP4Tags
from plexapi.audio import Track

from ds_tools.caching import ClearableCachedPropertyMixin
from ds_tools.compat import cached_property
from tz_aware_dt import format_duration
from ...constants import tag_name_map
from ...text import Name
from ..exceptions import InvalidTagName, TagException, TagNotFound, TagValueException, UnsupportedTagForFileType
from .bpm import get_bpm
from .parsing import split_artists, AlbumName
from .patterns import EXTRACT_PART_MATCH, LYRIC_URL_MATCH, compiled_fnmatch_patterns, cleanup_album_name
from .utils import (
    FileBasedObject, MusicFileProperty, RATING_RANGES, TYPED_TAG_MAP, TextTagProperty, _NotSet, ON_WINDOWS,
    stars_from_256, tag_repr, parse_file_date, FILE_TYPE_TAG_ID_TO_NAME_MAP, print_tag_changes
)

__all__ = ['SongFile']
log = logging.getLogger(__name__)


class SongFile(ClearableCachedPropertyMixin, FileBasedObject):
    """Adds some properties/methods to mutagen.File types that facilitate other functions"""
    __instances = {}  # type: Dict[Path, 'SongFile']
    _bpm = None
    tags = MusicFileProperty('tags')
    filename = __fspath__ = MusicFileProperty('filename')               # type: str
    length = MusicFileProperty('info.length')                           # type: float   # length of this song in seconds
    channels = MusicFileProperty('info.channels')                       # type: int
    bitrate = MusicFileProperty('info.bitrate')                         # type: int
    sample_rate = MusicFileProperty('info.sample_rate')                 # type: int
    tag_artist = TextTagProperty('artist', default=None)                # type: Optional[str]
    tag_album_artist = TextTagProperty('album_artist', default=None)    # type: Optional[str]
    tag_title = TextTagProperty('title', default=None)                  # type: Optional[str]
    tag_album = TextTagProperty('album', default=None)                  # type: Optional[str]
    date = TextTagProperty('date', parse_file_date)                     # type: Optional[date]

    def __new__(cls, file_path: Union[Path, str], *args, **kwargs):
        file_path = Path(file_path).expanduser().resolve() if isinstance(file_path, str) else file_path
        try:
            return cls.__instances[file_path]
        except KeyError:
            try:
                music_file = File(file_path, *args, **kwargs)
            except Exception as e:
                log.debug(f'Error loading {file_path}: {e}')
                return None
            if not music_file:          # mutagen.File is a function that returns different obj types based on the given
                return None             # file path - it may return None
            obj = super().__new__(cls)
            obj._f = music_file
            obj.__dict__['path'] = file_path  # Prevent Path->str->Path conversion for custom Path subtypes
            cls.__instances[file_path] = obj
            return obj

    def __init__(self, file_path: Union[Path, str], *args, **kwargs):
        if not getattr(self, '_SongFile__initialized', False):
            self._album_dir = None
            self._in_album_dir = False
            self.__initialized = True

    def __getitem__(self, item):
        return self._f[item]

    def __repr__(self):
        return '<{}({!r})>'.format(self.__class__.__name__, self.rel_path)

    def __getnewargs__(self):
        # noinspection PyRedundantParentheses
        return (self.path.as_posix(),)

    def __getstate__(self):
        return None  # prevents calling __setstate__ on unpickle; simpler for rebuilt obj to re-calculate cached attrs

    def rename(self, dest_path: Union[Path, str]):
        old_path = self.path
        if not isinstance(dest_path, Path):
            dest_path = Path(dest_path)

        dest_name = dest_path.name                      # on Windows, if the new path is only different by case,
        dest_path = dest_path.expanduser().resolve()    # .resolve() discards the new case
        dest_path = dest_path.with_name(dest_name)

        if not dest_path.parent.exists():
            dest_path.parent.mkdir(parents=True)

        use_temp = False
        if dest_path.exists():
            if dest_path.samefile(self.path) and ON_WINDOWS and dest_name != self.path.name:
                use_temp = True
            else:
                raise ValueError('Destination for {} already exists: {!r}'.format(self, dest_path.as_posix()))

        if use_temp:
            with TemporaryDirectory(dir=dest_path.parent.as_posix()) as tmp_dir:
                tmp_path = Path(tmp_dir).joinpath(dest_path.name)
                log.debug(f'Moving {self.path} to temp path={tmp_path} to work around case-insensitive fs')
                self.path.rename(tmp_path)
                tmp_path.rename(dest_path)
        else:
            self.path.rename(dest_path)

        self.clear_cached_properties()          # trigger self.path descriptor update (via FileBasedObject)
        new_path = dest_path
        # noinspection PyAttributeOutsideInit
        self._f = mutagen.File(new_path.as_posix())

        cls = type(self)
        del cls.__instances[old_path]
        cls.__instances[new_path] = self

    def save(self):
        self._f.tags.save(self._f.filename)

    @cached_property
    def length_str(self) -> str:
        """
        :return str: The length of this song in the format (HH:M)M:SS
        """
        length = format_duration(int(self._f.info.length))  # Most other programs seem to floor the seconds
        if length.startswith('00:'):
            length = length[3:]
        if length.startswith('0'):
            length = length[1:]
        return length

    @cached_property
    def tag_type(self) -> Optional[str]:
        tags = self._f.tags
        if isinstance(tags, MP4Tags):
            return 'mp4'
        elif isinstance(tags, ID3):
            return 'mp3'
        elif isinstance(tags, VCFLACDict):
            return 'flac'
        return None

    @cached_property
    def tag_version(self) -> str:
        tags = self._f.tags
        if isinstance(tags, MP4Tags):
            return 'MP4'
        elif isinstance(tags, ID3):
            return 'ID3v{}.{}'.format(*tags.version[:2])
        elif isinstance(tags, VCFLACDict):
            return 'FLAC'
        else:
            return tags.__name__

    def delete_tag(self, tag_id: str):
        tag_type = self.tag_type
        if tag_type == 'mp3':
            self.tags.delall(tag_id)
        elif tag_type in ('mp4', 'flac'):
            del self.tags[tag_id]
        else:
            raise TypeError(f'Cannot delete tag_id={tag_id!r} for {self} because its tag type={tag_type!r}')

    def remove_tags(self, tag_ids: Iterable[str], dry_run=False, log_lvl=logging.DEBUG) -> bool:
        prefix = '[DRY RUN] Would remove' if dry_run else 'Removing'
        to_remove = {
            tag_id: val if isinstance(val, list) else [val]
            for tag_id in sorted(tag_ids) if (val := self.tags.get(tag_id) or self.tags_for_id(tag_id))
        }
        if to_remove:
            rm_str = ', '.join(f'{tag_id}: {tag_repr(val)}' for tag_id, vals in to_remove.items() for val in vals)
            info_str = ', '.join(f'{tag_id} ({len(vals)})' for tag_id, vals in to_remove.items())

            log.info(f'{prefix} tags from {self}: {info_str}')
            log.debug(f'\t{self}: {rm_str}')
            if not dry_run:
                for tag_id in to_remove:
                    self.delete_tag(tag_id)
                self.save()
            return True
        else:
            log.log(log_lvl, f'{self}: Did not have the tags specified for removal')
            return False

    def set_text_tag(self, tag: str, value, by_id=False):
        tag_id = tag if by_id else self.normalize_tag_id(tag)
        tags = self._f.tags
        tag_type = self.tag_type
        if tag_type in ('mp4', 'flac'):
            if not isinstance(value, list):
                value = [value]
            try:
                tags[tag_id] = value
            except Exception as e:
                log.error(f'Error setting tag={tag_id!r} on {self} to {value=!r}: {e}')
                raise
        elif tag_type == 'mp3':
            try:
                tag_cls = getattr(mutagen.id3._frames, tag_id.upper())
            except AttributeError as e:
                raise ValueError(f'Invalid tag for {self}: {tag} (no frame class found for it)') from e
            else:
                # log.debug(f'{self}: Setting {tag_cls.__name__} = {value!r}')
                tags[tag_id] = tag_cls(text=str(value))
        else:
            raise TypeError(f'Unable to set {tag!r} for {self} because its extension is {tag_type!r}')

    def normalize_tag_id(self, tag_name_or_id: str) -> str:
        if type_to_id := TYPED_TAG_MAP.get(tag_name_or_id.lower()):
            try:
                return type_to_id[self.tag_type]
            except KeyError as e:
                raise UnsupportedTagForFileType(tag_name_or_id, self) from e
        id_to_name = FILE_TYPE_TAG_ID_TO_NAME_MAP[self.tag_type]
        if tag_name_or_id in id_to_name:
            return tag_name_or_id
        id_upper = tag_name_or_id.upper()
        if id_upper in id_to_name:
            return id_upper
        if self.tag_type == 'mp3':
            if id_upper in Frames:
                return id_upper
            raise InvalidTagName(id_upper, self)
        else:
            return tag_name_or_id

    def normalize_tag_name(self, tag_name_or_id: str) -> str:
        if tag_name_or_id in TYPED_TAG_MAP:
            return tag_name_or_id
        id_lower = tag_name_or_id.lower()
        if id_lower in TYPED_TAG_MAP:
            return id_lower
        id_to_name = FILE_TYPE_TAG_ID_TO_NAME_MAP[self.tag_type]
        for val in (tag_name_or_id, id_lower, tag_name_or_id.upper()):
            if val in id_to_name:
                return id_to_name[val]
        return tag_name_or_id

    def tag_name_to_id(self, tag_name: str) -> str:
        """
        :param str tag_name: The file type-agnostic name of a tag, e.g., 'title' or 'date'
        :return str: The tag ID appropriate for this file based on whether it is an MP3 or MP4
        """
        try:
            type2id = TYPED_TAG_MAP[tag_name]
        except KeyError as e:
            raise InvalidTagName(tag_name, self) from e
        try:
            return type2id[self.tag_type]
        except KeyError as e:
            raise UnsupportedTagForFileType(tag_name, self) from e

    def tags_for_id(self, tag_id: str):
        """
        :param str tag_id: A tag ID
        :return list: All tags from this file with the given ID
        """
        if self.tag_type == 'mp3':
            return self._f.tags.getall(tag_id.upper())         # all MP3 tags are uppercase; some MP4 tags are mixed case
        return self._f.tags.get(tag_id, [])                    # MP4Tags doesn't have getall() and always returns a list

    def tags_named(self, tag_name: str):
        """
        :param str tag_name: A tag name; see :meth:`.tag_name_to_id` for mapping of names to IDs
        :return list: All tags from this file with the given name
        """
        return self.tags_for_id(self.normalize_tag_id(tag_name))

    def get_tag(self, tag: str, by_id=False):
        """
        :param str tag: The name of the tag to retrieve, or the tag ID if by_id is set to True
        :param bool by_id: The provided value was a tag ID rather than a tag name
        :return: The tag object if there was a single instance of the tag with the given name/ID
        :raises: :class:`TagValueException` if multiple tags were found with the given name/ID
        :raises: :class:`TagNotFound` if no tags were found with the given name/ID
        """
        tags = self.tags_for_id(tag) if by_id else self.tags_named(tag)
        if len(tags) > 1:
            fmt = 'Multiple {!r} tags found for {}: {}'
            raise TagValueException(fmt.format(tag, self, ', '.join(map(repr, tags))))
        elif not tags:
            raise TagNotFound('No {!r} tags were found for {}'.format(tag, self))
        return tags[0]

    def tag_text(self, tag: str, strip=True, by_id=False, default=_NotSet):
        """
        :param str tag: The name of the tag to retrieve, or the tag ID if by_id is set to True
        :param bool strip: Strip leading/trailing spaces from the value before returning it
        :param bool by_id: The provided value was a tag ID rather than a tag name
        :param None|Str default: Default value to return when a TagValueException would otherwise be raised
        :return str: The text content of the tag with the given name if there was a single value
        :raises: :class:`TagValueException` if multiple values existed for the given tag
        """
        try:
            _tag = self.get_tag(tag, by_id)
        except TagNotFound as e:
            if default is not _NotSet:
                return default
            raise e
        vals = getattr(_tag, 'text', _tag)
        if not isinstance(vals, list):
            vals = [vals]
        vals = list(map(str, vals))
        if len(vals) > 1:
            msg = 'Multiple {!r} values found for {}: {}'.format(tag, self, ', '.join(map(repr, vals)))
            if default is not _NotSet:
                log.warning(msg)
                return default
            raise TagValueException(msg)
        elif not vals:
            if default is not _NotSet:
                return default
            raise TagValueException('No {!r} tag values were found for {}'.format(tag, self))
        return vals[0].strip() if strip else vals[0]

    def all_tag_text(self, tag_name: str, suppress_exc=True):
        try:
            for tag in self.tags_named(tag_name):
                yield from tag
        except KeyError as e:
            if suppress_exc:
                log.debug('{} has no {} tags - {}'.format(self, tag_name, e))
            else:
                raise e

    def iter_clean_tags(self) -> Iterator[Tuple[str, str, Any]]:
        mp3 = self.tag_type == 'mp3'
        normalize_tag_name = self.normalize_tag_name
        for tag, value in self._f.tags.items():
            _tag = tag[:4] if mp3 else tag
            yield _tag, normalize_tag_name(_tag), value

    @cached_property
    def all_artists(self) -> Set[Name]:
        return self.album_artists.union(self.artists)

    @cached_property
    def album_artists(self) -> Set[Name]:
        if album_artist := self.tag_album_artist:
            return set(split_artists(album_artist))
        return set()

    @cached_property
    def artists(self) -> Set[Name]:
        if artist := self.tag_artist:
            artists = set(split_artists(artist))
            # noinspection PyUnresolvedReferences
            if (album := self.album) and album.feat:
                artists.update(album.feat)
            return artists
        return set()

    @cached_property
    def album_artist(self) -> Optional[Name]:
        if (artists := self.album_artists) and len(artists) == 1:
            return next(iter(artists))
        return None

    @cached_property
    def artist(self) -> Optional[Name]:
        if (artists := self.artists) and len(artists) == 1:
            return next(iter(artists))
        return None

    @cached_property
    def album(self) -> Optional[AlbumName]:
        if album := self.tag_album:
            return AlbumName.parse(album, self.tag_artist)
        return None

    @cached_property
    def year(self) -> Optional[int]:
        try:
            return self.date.year
        except Exception:
            return None

    @cached_property
    def track_num(self) -> int:
        orig = track = self.tag_text('track', default=None)
        if track:
            if '/' in track:
                track = track.split('/', 1)[0].strip()
            if ',' in track:
                track = track.split(',', 1)[0].strip()
            if track.startswith('('):
                track = track[1:].strip()

            try:
                track = int(track)
            except Exception as e:
                log.debug(f'{self}: Error converting track num={orig!r} [{track!r}] to int: {e}')
                track = 0
        return track or 0

    @cached_property
    def disk_num(self) -> int:
        orig = disk = self.tag_text('disk', default=None)
        if disk:
            if '/' in disk:
                disk = disk.split('/')[0].strip()
            if ',' in disk:
                disk = disk.split(',')[0].strip()
            if disk.startswith('('):
                disk = disk[1:].strip()

            try:
                disk = int(disk)
            except Exception as e:
                log.debug(f'{self}: Error converting disk num={orig!r} [{disk!r}] to int: {e}')
                disk = 0
        return disk or 0

    @property
    def rating(self) -> Optional[int]:
        """The rating for this track on a scale of 1-255"""
        if isinstance(self._f.tags, MP4Tags):
            try:
                return self._f.tags['POPM'][0]
            except KeyError:
                return None
        else:
            try:
                return self.get_tag('POPM', True).rating
            except TagNotFound:
                return None

    @rating.setter
    def rating(self, value: Union[int, float]):
        if isinstance(self._f.tags, MP4Tags):
            self._f.tags['POPM'] = [value]
        else:
            try:
                tag = self.get_tag('POPM', True)
            except TagNotFound:
                self._f.tags.add(POPM(rating=value))
            else:
                tag.rating = value
        self.save()

    @property
    def star_rating_10(self) -> Optional[int]:
        if (rating := self.rating) is not None:
            return stars_from_256(rating, 10)
        return None

    @star_rating_10.setter
    def star_rating_10(self, value: Union[int, float]):
        if not isinstance(value, (int, float)) or not 0 < value < 11:
            raise ValueError('Star ratings must be ints on a scale of 1-10; invalid value: {}'.format(value))
        elif value == 1:
            self.rating = 1
        else:
            base, extra = divmod(int(value), 2)
            self.rating = RATING_RANGES[base - 1][2] + extra

    @property
    def star_rating(self) -> Optional[int]:
        """
        This implementation uses the ranges specified here: https://en.wikipedia.org/wiki/ID3#ID3v2_rating_tag_issue

        :return int|None: The star rating equivalent of this track's POPM rating
        """
        if (rating := self.rating) is not None:
            return stars_from_256(rating)
        return None

    @star_rating.setter
    def star_rating(self, value: Union[int, float]):
        """
        This implementation uses the same values specified in the following link, except for 1 star, which uses 15
        instead of 1: https://en.wikipedia.org/wiki/ID3#ID3v2_rating_tag_issue

        :param int value: The number of stars to set
        """
        if not isinstance(value, (int, float)) or not 0 < value < 5.5:
            raise ValueError('Star ratings must on a scale of 1-5; invalid value: {}'.format(value))
        elif int(value) != value:
            if int(value) + 0.5 == value:
                self.star_rating_10 = int(value * 2)
            else:
                raise ValueError('Star ratings must be a multiple of 0.5; invalid value: {}'.format(value))
        else:
            self.rating = RATING_RANGES[int(value) - 1][2]

    def tagless_sha256sum(self):
        with self.path.open('rb') as f:
            tmp = BytesIO(f.read())

        try:
            mutagen.File(tmp).tags.delete(tmp)
        except AttributeError as e:
            log.error('Error determining tagless sha256sum for {}: {}'.format(self._f.filename, e))
            return self._f.filename

        tmp.seek(0)
        return sha256(tmp.read()).hexdigest()

    def sha256sum(self):
        with self.path.open('rb') as f:
            return sha256(f.read()).hexdigest()

    # @cached_property
    # def acoustid_fingerprint(self):
    #     """Returns the 2-tuple of this file's (duration, fingerprint)"""
    #     return acoustid.fingerprint_file(self.filename)

    @classmethod
    def for_plex_track(cls, track_or_rel_path: Union[Track, str], root: Union[str, Path]) -> 'SongFile':
        if ON_WINDOWS:
            if isinstance(root, Path):  # Path does not work for network shares in Windows
                root = root.as_posix()
            if root.startswith('/') and not root.startswith('//'):
                root = '/' + root

        if isinstance(track_or_rel_path, str):
            rel_path = track_or_rel_path
        else:
            rel_path = track_or_rel_path.media[0].parts[0].file
        path = os.path.join(root, rel_path[1:] if rel_path.startswith('/') else rel_path)
        return cls(path)

    @cached_property
    def extended_repr(self):
        try:
            info = '[{!r} by {}, in {!r}]'.format(self.tag_title, self.tag_artist, self.album_name_cleaned)
        except Exception as e:
            info = ''
        return '<{}({!r}){}>'.format(self.__class__.__name__, self.rel_path, info)

    @cached_property
    def album_name_cleaned(self):
        return cleanup_album_name(self.tag_album, self.tag_artist) or self.tag_album

    @cached_property
    def album_name_cleaned_plus_and_part(self):
        """Tuple of title, part"""
        return _extract_album_part(self.album_name_cleaned)

    def cleanup_lyrics(self, dry_run=False):
        prefix, upd_msg = ('[DRY RUN] ', 'Would update') if dry_run else ('', 'Updating')
        changes = 0
        tag_type = self.tag_type
        new_lyrics = []
        for lyric_tag in self.tags_named('lyrics'):
            lyric = lyric_tag.text if tag_type == 'mp3' else lyric_tag
            if m := LYRIC_URL_MATCH(lyric):
                new_lyric = m.group(1).strip() + '\r\n'
                log.info(f'{prefix}{upd_msg} lyrics for {self} from {tag_repr(lyric)!r} to {tag_repr(new_lyric)!r}')
                if not dry_run:
                    if tag_type == 'mp3':
                        lyric_tag.text = new_lyric
                    else:
                        new_lyrics.append(new_lyric)
                    changes += 1
            else:
                new_lyrics.append(lyric)

        if changes and not dry_run:
            log.info('Saving changes to lyrics in {}'.format(self))
            if tag_type == 'mp4':
                self.set_text_tag('lyrics', new_lyrics)
            self.save()

    def bpm(self, save=True, calculate=True) -> Optional[int]:
        """
        :param bool save: If the BPM was not already stored in a tag, save the calculated BPM in a tag.
        :param bool calculate: If the BPM was not already stored in a tag, calculate it
        :return int: This track's BPM from a tag if available, or calculated
        """
        try:
            bpm = int(self.tag_text('bpm'))
        except TagException:
            if calculate:
                if not (bpm := self._bpm):
                    bpm = self._bpm = get_bpm(self.path, self.sample_rate)
                if save:
                    self.set_text_tag('bpm', bpm)
                    log.debug(f'Saving {bpm=} for {self}')
                    self.save()
            else:
                bpm = None
        return bpm

    def update_tags(self, name_value_map, dry_run=False, no_log=None, none_level=19):
        """
        :param dict name_value_map: Mapping of {tag name: new value}
        :param bool dry_run: Whether tags should actually be updated
        :param container no_log: Names of tags for which updates should not be logged
        :param int none_level: If no changes need to be made, the log level for the message stating that.
        """
        to_update = {}
        for tag_name, new_value in sorted(name_value_map.items()):
            file_value = self.tag_text(tag_name, default=None)
            cmp_value = str(new_value) if tag_name in ('disk', 'track') else new_value
            if cmp_value != file_value:
                to_update[tag_name] = (file_value, new_value)

        if to_update:
            no_log = no_log or ()
            if to_log := {k: v for k, v in to_update.items() if k not in no_log}:
                print_tag_changes(self, to_log, dry_run)
            do_save = True
            for tag_name, (file_value, new_value) in to_update.items():
                if not dry_run:
                    try:
                        self.set_text_tag(tag_name, new_value, by_id=False)
                    except TagException as e:
                        do_save = False
                        log.error(f'Error setting tag={tag_name} on {self}: {e}')
            if do_save and not dry_run:
                self.save()
        else:
            log.log(none_level, f'No changes to make for {self.extended_repr}')

    def get_tag_updates(self, tag_ids, value, patterns=None, partial=False):
        if partial and not patterns:
            raise ValueError('Unable to perform partial tag update without any patterns')
        patterns = compiled_fnmatch_patterns(patterns)
        to_update = {}
        for tag_id in tag_ids:
            if names_by_type := TYPED_TAG_MAP.get(tag_id):
                tag_id = names_by_type[self.tag_type]
            if not (tag_name := tag_name_map.get(tag_id)):
                raise ValueError(f'Invalid tag ID: {tag_id}')
            norm_name = self.normalize_tag_name(tag_id)

            if current_vals := self.tags_for_id(tag_id):
                if len(current_vals) > 1:
                    log.warning(f'Found multiple values for {tag_id}/{tag_name} in {self} - using first value')

                current_val = current_vals[0]
                current_text = current_val.text[0]
                new_text = current_text
                if partial:
                    for pat in patterns:
                        new_text = pat.sub(value, new_text)
                else:
                    if patterns:
                        if any(pat.search(current_text) for pat in patterns):
                            new_text = value
                    else:
                        new_text = value

                if new_text != current_text:
                    to_update[norm_name] = new_text
            else:
                to_update[norm_name] = value

        return to_update

    def update_tags_with_value(self, tag_ids, value, patterns=None, partial=False, dry_run=False):
        updates = self.get_tag_updates(tag_ids, value, patterns, partial)
        self.update_tags(updates, dry_run)


def _extract_album_part(title):
    part = None
    if m := EXTRACT_PART_MATCH(title):
        title, part = map(str.strip, m.groups())
    if title.endswith(' -'):
        title = title[:-1].strip()
    return title, part


if __name__ == '__main__':
    from ..patches import apply_mutagen_patches
    apply_mutagen_patches()
