"""
:author: Doug Skrypa
"""

"""
:author: Doug Skrypa
"""

import logging
import os
import re
from hashlib import sha256
from io import BytesIO
from pathlib import Path

import mutagen
import mutagen.id3._frames
from mutagen.id3 import ID3, POPM
from mutagen.mp4 import MP4Tags

from ds_tools.caching import ClearableCachedPropertyMixin
from ds_tools.compat import cached_property
from tz_aware_dt import format_duration, datetime_with_tz
from ..exceptions import *

__all__ = ['BaseSongFile']
log = logging.getLogger(__name__)

RATING_RANGES = [(1, 31, 15), (32, 95, 64), (96, 159, 128), (160, 223, 196), (224, 255, 255)]
TYPED_TAG_MAP = {   # See: https://wiki.hydrogenaud.io/index.php?title=Tag_Mapping
    'title': {'mp4': '\xa9nam', 'mp3': 'TIT2'},
    'date': {'mp4': '\xa9day', 'mp3': 'TDRC'},
    'genre': {'mp4': '\xa9gen', 'mp3': 'TCON'},
    'album': {'mp4': '\xa9alb', 'mp3': 'TALB'},
    'artist': {'mp4': '\xa9ART', 'mp3': 'TPE1'},
    'album_artist': {'mp4': 'aART', 'mp3': 'TPE2'},
    'track': {'mp4': 'trkn', 'mp3': 'TRCK'},
    'disk': {'mp4': 'disk', 'mp3': 'TPOS'},
    'grouping': {'mp4': '\xa9grp', 'mp3': 'TIT1'},
    'album_sort_order': {'mp4': 'soal', 'mp3': 'TSOA'},
    'track_sort_order': {'mp4': 'sonm', 'mp3': 'TSOT'},
    'album_artist_sort_order': {'mp4': 'soaa', 'mp3': 'TSO2'},
    'track_artist_sort_order': {'mp4': 'soar', 'mp3': 'TSOP'},
}
_NotSet = object()


class BaseSongFile(ClearableCachedPropertyMixin):
    """Adds some properties/methods to mutagen.File types that facilitate other functions"""
    __instances = {}

    def __new__(cls, file_path, *args, **kwargs):
        file_path = Path(file_path).expanduser().as_posix()
        if file_path not in cls.__instances:
            try:
                music_file = mutagen.File(file_path, *args, **kwargs)
            except Exception as e:
                log.debug('Error loading {}: {}'.format(file_path, e))
                music_file = None

            if music_file:
                obj = super().__new__(cls)
                obj._f = music_file
                cls.__instances[file_path] = obj
                return obj
            else:
                return None
        else:
            return cls.__instances[file_path]

    def __init__(self, file_path, *args, **kwargs):
        if not getattr(self, '_BaseSongFile__initialized', False):
            self._album_dir = None
            self._in_album_dir = False
            self.__initialized = True

    def __getitem__(self, item):
        return self._f[item]

    def __repr__(self):
        return '<{}({!r})>'.format(type(self).__name__, self.rel_path)

    @property
    def tags(self):
        return self._f.tags

    @property
    def filename(self):
        return self._f.filename

    @cached_property
    def extended_repr(self):
        try:
            info = '[{!r} by {}, in {!r}]'.format(self.tag_title, self.tag_artist, self.album_name_cleaned)
        except Exception as e:
            info = ''
        return '<{}({!r}){}>'.format(type(self).__name__, self.rel_path, info)

    def rename(self, dest_path):
        old_path = self.path.as_posix()
        if not isinstance(dest_path, Path):
            dest_path = Path(dest_path).expanduser().resolve()

        if not dest_path.parent.exists():
            os.makedirs(dest_path.parent.as_posix())
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
    def path(self):
        return Path(self._f.filename).resolve()

    @property
    def rel_path(self):
        try:
            return self.path.relative_to(Path('.').resolve()).as_posix()
        except Exception as e:
            return self.path.as_posix()

    def basename(self, no_ext=False, trim_prefix=False):
        basename = self.path.stem if no_ext else self.path.name
        if trim_prefix:
            m = re.match(r'\d+\.?\s*(.*)', basename)
            if m:
                basename = m.group(1)
        return basename

    @cached_property
    def ext(self):
        if isinstance(self._f.tags, MP4Tags):
            return self.path.suffix[1:]
        elif isinstance(self._f.tags, ID3):
            return 'mp3'
        return None

    @cached_property
    def tag_artist(self):
        return self.tag_text('artist')

    @cached_property
    def tag_title(self):
        return self.tag_text('title')

    def _cleanup_album_name(self, album):
        m = re.match(r'^\[\d{4}[0-9.]*\](.*)', album, re.IGNORECASE)
        if m:
            album = m.group(1).strip()

        m = re.match(r'(.*)\s*\[.*Album(?: repackage)?\]', album, re.IGNORECASE)
        if m:
            album = m.group(1).strip()

        m = re.match(r'^(.*?)-?\s*(?:the)?\s*[0-9](?:st|nd|rd|th)\s+\S*\s*album\s*(?:repackage)?\s*(.*)$', album, re.I)
        if m:
            album = ' '.join(map(str.strip, m.groups())).strip()

        m = re.search(r'((?:^|\s+)\d+\s*집(?:$|\s+))', album)  # {num}집 == nth album
        if m:
            album = album.replace(m.group(1), ' ').strip()

        m = re.match(r'(.*)(\s-\s*(?:EP|Single))$', album, re.IGNORECASE)
        if m:
            album = m.group(1)

        m = re.match(r'^(.*)\sO\.S\.T\.?(\s.*|$)', album, re.IGNORECASE)
        if m:
            album = '{} OST{}'.format(*m.groups())

        for pat in ('^(.*) `(.*)`$', '^(.*) - (.*)$'):
            m = re.match(pat, album)
            if m:
                group, title = m.groups()
                if group in self.tag_artist:
                    album = title
                break

        return album.replace(' : ', ': ').strip()

    def _extract_album_part(self, title):
        part = None
        m = re.match(r'^(.*)\s+((?:Part|Code No)\.?\s*\d+)$', title, re.IGNORECASE)
        if m:
            title = m.group(1).strip()
            part = m.group(2).strip()

        if title.endswith(' -'):
            title = title[:-1].strip()
        return title, part

    @cached_property
    def album_name_cleaned(self):
        cleaned = self._cleanup_album_name(self.tag_text('album'))
        return cleaned if cleaned else self.tag_text('album')

    @cached_property
    def album_name_cleaned_plus_and_part(self):
        return self._extract_album_part(self.album_name_cleaned)

    @cached_property
    def dir_name_cleaned(self):
        return self._cleanup_album_name(self.path.parent.name)

    @cached_property
    def dir_name_cleaned_plus_and_part(self):
        return self._extract_album_part(self.dir_name_cleaned)

    def set_title(self, title):
        self.set_text_tag('title', title, by_id=False)

    @property
    def length(self):
        """
        :return float: The length of this song in seconds
        """
        return self._f.info.length

    @cached_property
    def length_str(self):
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
    def _tag_type(self):
        if isinstance(self._f.tags, MP4Tags):
            return 'mp4'
        elif isinstance(self._f.tags, ID3):
            return 'mp3'
        return None

    def set_text_tag(self, tag, value, by_id=False):
        tag_id = tag if by_id else self.tag_name_to_id(tag)
        if isinstance(self._f.tags, MP4Tags):
            self._f.tags[tag_id] = value
        elif self.ext == 'mp3':
            try:
                tag_cls = getattr(mutagen.id3._frames, tag_id.upper())
            except AttributeError as e:
                raise ValueError('Invalid tag for {}: {} (no frame class found for it)'.format(self, tag)) from e
            else:
                self._f.tags[tag_id] = tag_cls(text=value)
        else:
            raise TypeError('Unable to set {!r} for {} because its extension is {!r}'.format(tag, self, self.ext))

    def tag_name_to_id(self, tag_name):
        """
        :param str tag_name: The file type-agnostic name of a tag, e.g., 'title' or 'date'
        :return str: The tag ID appropriate for this file based on whether it is an MP3 or MP4
        """
        try:
            type2id = TYPED_TAG_MAP[tag_name]
        except KeyError as e:
            raise InvalidTagName(tag_name, self) from e
        try:
            return type2id[self._tag_type]
        except KeyError as e:
            raise UnsupportedTagForFileType(tag_name, self) from e

    def tags_for_id(self, tag_id):
        """
        :param str tag_id: A tag ID
        :return list: All tags from this file with the given ID
        """
        if self.ext == 'mp3':
            return self._f.tags.getall(tag_id.upper())         # all MP3 tags are uppercase; some MP4 tags are mixed case
        return self._f.tags.get(tag_id, [])                    # MP4Tags doesn't have getall() and always returns a list

    def tags_named(self, tag_name):
        """
        :param str tag_name: A tag name; see :meth:`.tag_name_to_id` for mapping of names to IDs
        :return list: All tags from this file with the given name
        """
        return self.tags_for_id(self.tag_name_to_id(tag_name))

    def get_tag(self, tag, by_id=False):
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

    def tag_text(self, tag, strip=True, by_id=False, default=_NotSet):
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

    def all_tag_text(self, tag_name, suppress_exc=True):
        try:
            for tag in self.tags_named(tag_name):
                yield from tag
        except KeyError as e:
            if suppress_exc:
                log.debug('{} has no {} tags - {}'.format(self, tag_name, e))
            else:
                raise e

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

    @cached_property
    def date(self):
        date_str = self.tag_text('date')
        return datetime_with_tz(date_str, '%Y%m%d')

    @cached_property
    def year(self):
        try:
            return self.date.year
        except Exception:
            return None

    @cached_property
    def track_num(self):
        track = self.tag_text('track', default=None)
        if track:
            if '/' in track:
                track = track.split('/')[0].strip()
            if ',' in track:
                track = track.split(',')[0].strip()
            if track.startswith('('):
                track = track[1:].strip()

            try:                        # Strip any leading 0s
                _track = int(track)
            except Exception:
                pass
            else:
                track = str(_track)

        return track

    @cached_property
    def disk_num(self):
        disk = self.tag_text('disk', default=None)
        if disk:
            if '/' in disk:
                disk = disk.split('/')[0].strip()
            if ',' in disk:
                disk = disk.split(',')[0].strip()
            if disk.startswith('('):
                disk = disk[1:].strip()
        return disk

    @property
    def rating(self):
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
    def rating(self, value):
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
    def star_rating_10(self):
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
    def star_rating_10(self, value):
        if not isinstance(value, (int, float)) or not 0 < value < 11:
            raise ValueError('Star ratings must be ints on a scale of 1-10; invalid value: {}'.format(value))
        elif value == 1:
            self.rating = 1
        else:
            base, extra = divmod(int(value), 2)
            self.rating = RATING_RANGES[base - 1][2] + extra

    @property
    def star_rating(self):
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
    def star_rating(self, value):
        """
        This implementation uses the same values specified in the following link, except for 1 star, which uses 15
        instead of 1: https://en.wikipedia.org/wiki/ID3#ID3v2_rating_tag_issue

        :param int value: The number of stars to set
        :return:
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
