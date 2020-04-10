"""
:author: Doug Skrypa
"""

import logging
from datetime import datetime, date
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from typing import Optional, Union, Iterator, Tuple, Set, Mapping, Sequence, Any

import mutagen
import mutagen.id3._frames
from mutagen import File
from mutagen.flac import VCFLACDict
from mutagen.id3 import ID3, POPM
from mutagen.mp4 import MP4Tags

from ds_tools.caching import ClearableCachedPropertyMixin
from ds_tools.compat import cached_property
from tz_aware_dt import format_duration
from ...text import Name
from ..exceptions import *
from .parsing import split_artists, AlbumName
from .utils import FileBasedObject, MusicFileProperty, RATING_RANGES, TYPED_TAG_MAP, TextTagProperty, _NotSet

__all__ = ['BaseSongFile']
log = logging.getLogger(__name__)


class BaseSongFile(ClearableCachedPropertyMixin, FileBasedObject):
    """Adds some properties/methods to mutagen.File types that facilitate other functions"""
    __instances = {}
    tags = MusicFileProperty('tags')
    filename = __fspath__ = MusicFileProperty('filename')               # type: str
    length = MusicFileProperty('info.length')                           # type: float   # length of this song in seconds
    tag_artist = TextTagProperty('artist', default=None)                # type: Optional[str]
    tag_album_artist = TextTagProperty('album_artist', default=None)    # type: Optional[str]
    tag_title = TextTagProperty('title', default=None)                  # type: Optional[str]
    tag_album = TextTagProperty('album', default=None)                  # type: Optional[str]
    date = TextTagProperty('date', lambda d: datetime.strptime(d, '%Y%m%d').date())     # type: date

    def __new__(cls, file_path: Union[Path, str], *args, **kwargs):
        file_path = (Path(file_path).expanduser() if isinstance(file_path, str) else file_path).as_posix()
        try:
            return cls.__instances[file_path]
        except KeyError:
            try:
                music_file = File(file_path, *args, **kwargs)
            except Exception as e:
                log.debug('Error loading {}: {}'.format(file_path, e))
                return None
            if not music_file:          # mutagen.File is a function that returns different obj types based on the given
                return None             # file path - it may return None
            obj = super().__new__(cls)
            obj._f = music_file
            cls.__instances[file_path] = obj
            return obj

    def __init__(self, file_path: Union[Path, str], *args, **kwargs):
        if not getattr(self, '_BaseSongFile__initialized', False):
            self._album_dir = None
            self._in_album_dir = False
            self.__initialized = True

    def __getitem__(self, item):
        return self._f[item]

    def __repr__(self):
        return '<{}({!r})>'.format(self.__class__.__name__, self.rel_path)

    def rename(self, dest_path: Union[Path, str]):
        old_path = self.path.as_posix()
        if not isinstance(dest_path, Path):
            dest_path = Path(dest_path)
        dest_path = dest_path.expanduser().resolve()
        if not dest_path.parent.exists():
            dest_path.parent.mkdir(parents=True)
        if dest_path.exists():
            raise ValueError('Destination for {} already exists: {!r}'.format(self, dest_path.as_posix()))

        self.path.rename(dest_path)
        self.clear_cached_properties()
        new_path = dest_path.as_posix()
        # noinspection PyAttributeOutsideInit
        self._f = mutagen.File(new_path)

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

    def set_text_tag(self, tag: str, value, by_id=False):
        tag_id = tag if by_id else self.tag_name_to_id(tag)
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
                tags[tag_id] = tag_cls(text=value)
        else:
            raise TypeError(f'Unable to set {tag!r} for {self} because its extension is {tag_type!r}')

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
        return self.tags_for_id(self.tag_name_to_id(tag_name))

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

    def iter_clean_tags(self) -> Iterator[Tuple[str, Any]]:
        for tag, value in self._f.tags.items():
            yield tag[:4], value

    @cached_property
    def artists(self) -> Set[Name]:
        artists = set()
        if artist := self.tag_artist:
            artists.update(split_artists(artist))
        if album_artist := self.tag_album_artist:
            artists.update(split_artists(album_artist))
        return artists

    @cached_property
    def artist(self) -> Optional[Name]:
        if (artists := self.artists) and len(artists) == 1:
            return next(iter(artists))
        return None

    @cached_property
    def album(self) -> Optional[AlbumName]:
        if album := self.tag_album:
            return AlbumName.parse(album)
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
        star_rating_5 = self.star_rating
        if star_rating_5 is None:
            return None
        star_rating_10 = star_rating_5 * 2
        a, b, c = RATING_RANGES[star_rating_5 - 1]
        # log.debug('rating = {}, stars/5 = {}, a={}, b={}, c={}'.format(self.rating, star_rating_5, a, b, c))
        if star_rating_5 == 1 and self.rating < c:
            return 1
        return star_rating_10 + 1 if self.rating > c else star_rating_10

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
        rating = self.rating
        if rating is not None:
            for stars, (a, b, c) in enumerate(RATING_RANGES):
                if a <= rating <= b:
                    return stars + 1
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


if __name__ == '__main__':
    from ..patches import apply_mutagen_patches
    apply_mutagen_patches()
