"""
:author: Doug Skrypa
"""

import logging
import os
from datetime import date
from functools import cached_property
from hashlib import sha256
from io import BytesIO
from itertools import chain
from pathlib import Path
from platform import system
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Optional, Union, Iterator, Any, Iterable, Collection

from mutagen import File, FileType
from mutagen.flac import VCFLACDict, FLAC, Picture
from mutagen.id3 import ID3, POPM, Frames, _frames, ID3FileType, APIC, PictureType, Encoding
from mutagen.id3._specs import MultiSpec, Spec
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4Tags, MP4, MP4Cover, AtomDataType, MP4FreeForm
from plexapi.audio import Track

from ds_tools.caching.mixins import ClearableCachedPropertyMixin
from ds_tools.fs.paths import iter_files, Paths
from ds_tools.output.formatting import readable_bytes
from tz_aware_dt import format_duration
from ...constants import MP3_TAG_DISPLAY_NAME_MAP, TYPED_TAG_MAP, TYPED_TAG_DISPLAY_NAME_MAP, TAG_NAME_DISPLAY_NAME_MAP
from ...text.name import Name
from ..cover import prepare_cover_image
from ..exceptions import InvalidTagName, TagException, TagNotFound, TagValueException, UnsupportedTagForFileType
from ..parsing import split_artists, AlbumName
from ..paths import FileBasedObject
from .descriptors import MusicFileProperty, TextTagProperty, TagValuesProperty, _NotSet
from .patterns import EXTRACT_PART_MATCH, LYRIC_URL_MATCH, compiled_fnmatch_patterns, cleanup_album_name
from .utils import tag_repr, parse_file_date, tag_id_to_name_map_for_type, stars_to_256, stars_from_256

if TYPE_CHECKING:
    from PIL import Image

__all__ = ['SongFile', 'iter_music_files']
log = logging.getLogger(__name__)
ON_WINDOWS = system().lower() == 'windows'
MP4_STR_ENCODINGS = {AtomDataType.UTF8: 'utf-8', AtomDataType.UTF16: 'utf-16be'}  # noqa
MP4_MIME_FORMAT_MAP = {'image/jpeg': MP4Cover.FORMAT_JPEG, 'image/png': MP4Cover.FORMAT_PNG}
MutagenFile = Union[MP3, MP4, FLAC, FileType]
ImageTag = Union[APIC, MP4Cover, Picture]


class SongFile(ClearableCachedPropertyMixin, FileBasedObject):
    """Adds some properties/methods to mutagen.File types that facilitate other functions"""
    __instances = {}                                                    # type: dict[Path, 'SongFile']
    _bpm = None                                                         # type: Optional[int]
    _f = None                                                           # type: Optional[MutagenFile]
    _path = None                                                        # type: Optional[Path]
    tags = MusicFileProperty('tags')                                    # type: Union[ID3, MP4Tags, VCFLACDict]
    filename = MusicFileProperty('filename')                            # type: str
    length = MusicFileProperty('info.length')                           # type: float   # length of this song in seconds
    channels = MusicFileProperty('info.channels')                       # type: int
    bitrate = MusicFileProperty('info.bitrate')                         # type: int
    sample_rate = MusicFileProperty('info.sample_rate')                 # type: int
    tag_artist = TextTagProperty('artist', default=None)                # type: Optional[str]
    tag_album_artist = TextTagProperty('album_artist', default=None)    # type: Optional[str]
    tag_title = TextTagProperty('title', default=None)                  # type: Optional[str]
    tag_album = TextTagProperty('album', default=None)                  # type: Optional[str]
    tag_genre = TextTagProperty('genre', default=None)                  # type: Optional[str]
    tag_genres = TagValuesProperty('genre', default=None)               # type: list[str]
    date = TextTagProperty('date', parse_file_date, default=None)       # type: Optional[date]
    album_url = TextTagProperty('wiki:album', default=None)             # type: Optional[str]
    artist_url = TextTagProperty('wiki:artist', default=None)           # type: Optional[str]
    rating = TextTagProperty('rating', int, default=None, save=True)    # type: Optional[int]

    def __new__(cls, file_path: Union[Path, str], *args, options=_NotSet, **kwargs):
        file_path = Path(file_path).expanduser().resolve() if isinstance(file_path, str) else file_path
        try:
            return cls.__instances[file_path]
        except KeyError:
            options = (MP3, FLAC, MP4, ID3FileType) if options is _NotSet else options
            ipod = hasattr(file_path, '_ipod')
            filething = file_path.open('rb') if ipod else file_path
            error = True
            try:
                music_file = File(filething, *args, options=options, **kwargs)
            except Exception as e:
                log.debug(f'Error loading {file_path}: {e}')
                return None
            else:
                if music_file is None:      # mutagen.File is a function that returns different obj types based on the
                    return None             # given file path - it may return None
                error = False
            finally:
                if error and ipod:
                    filething.close()

            obj = super().__new__(cls)
            obj._init(music_file, file_path)
            cls.__instances[file_path] = obj
            return obj

    def __init__(self, file_path: Union[Path, str], *args, **kwargs):
        if not getattr(self, '_SongFile__initialized', False):
            self._album_dir = None
            self._in_album_dir = False
            self.__initialized = True

    def _init(self, mutagen_file: MutagenFile, path: Path):
        self._f = mutagen_file
        self._path = path

    def __getitem__(self, item):
        return self._f[item]

    def __repr__(self):
        return '<{}({!r})>'.format(self.__class__.__name__, self.rel_path)

    def __getnewargs__(self):
        # noinspection PyRedundantParentheses
        return (self.path.as_posix(),)

    def __getstate__(self):
        return None  # prevents calling __setstate__ on unpickle; simpler for rebuilt obj to re-calculate cached attrs

    @property
    def path(self) -> Path:
        return self._path

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
        self._init(File(dest_path, options=(self._f.__class__,)), dest_path)

        cls = type(self)
        del cls.__instances[old_path]
        cls.__instances[dest_path] = self

    def save(self):
        if self.tag_type == 'flac':
            self._f.save(self._f.filename)
        else:
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
        elif tags is None:
            return '[no tags]'
        else:
            return tags.__name__

    # region Add/Remove/Get Tags
    def delete_tag(self, tag_id: str, save: bool = False):
        tag_type = self.tag_type
        if tag_type == 'mp3':
            self.tags.delall(tag_id)
        elif tag_type in ('mp4', 'flac'):
            del self.tags[tag_id]
        else:
            raise TypeError(f'Cannot delete tag_id={tag_id!r} for {self} because its tag type={tag_type!r}')
        if save:
            self.save()

    def remove_tags(self, tag_ids: Iterable[str], dry_run=False, log_lvl=logging.DEBUG, remove_all=False) -> bool:
        tag_ids = list(map(self.normalize_tag_id, tag_ids))
        prefix = '[DRY RUN] Would remove' if dry_run else 'Removing'
        if remove_all:
            log.info(f'{prefix} ALL tags from {self}')
            if not dry_run:
                self._f.tags.delete(self._f.filename)
        else:
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

    def set_text_tag(self, tag: str, value, by_id=False, replace: bool = True, save: bool = False):
        tag_id = tag if by_id else self.normalize_tag_id(tag)
        tag_type = self.tag_type
        if tag_type in ('mp4', 'flac'):
            self._set_mp4_flac_text_tag(tag_id, value, replace)
        elif tag_type == 'mp3':
            self._set_mp3_text_tag(tag, tag_id, value, replace)
        else:
            raise TypeError(f'Unable to set {tag!r} for {self} because its extension is {tag_type!r}')
        if save:
            self.save()

    def _set_mp3_text_tag(self, tag: str, tag_id: str, value, replace: bool = True):
        tags = self._f.tags  # type: ID3
        tag_id = tag_id.upper()
        try:
            tag_id, desc = tag_id.split(':', 1)
        except ValueError:
            desc = None
        try:
            tag_cls = getattr(_frames, tag_id)
        except AttributeError as e:
            raise ValueError(f'Invalid tag for {self}: {tag} (no frame class found for it)') from e

        frame_spec = tag_cls._framespec
        spec_fields = {spec.name: spec for spec in frame_spec}
        if desc and 'desc' not in spec_fields:
            raise TypeError(f'Unhandled tag type - {tag=} has {desc=} but {tag_cls=} has {spec_fields=}')

        value_spec = frame_spec[-1]  # type: Spec  # main value field is usually last
        value_key = value_spec.name
        kwargs = {'encoding': Encoding.UTF8} if 'encoding' in spec_fields else {}  # noqa
        if not (isinstance(value, Collection) and not isinstance(value, str)):
            value = [value]

        if desc:
            kwargs['desc'] = desc
            values = tags.getall(tag_id)
            values = [v for v in values if v.desc != desc] if replace else values  # Keep any with a different desc
            for val in value:
                val_kwargs = kwargs.copy()
                val_kwargs[value_key] = val
                values.append(tag_cls(**val_kwargs))
        else:
            if replace:
                if not isinstance(value_spec.default, list) and isinstance(value, list) and len(value) == 1:
                    kwargs[value_key] = value[0]
                else:
                    kwargs[value_key] = sorted(map(str, value))
                log.debug(f'Creating tag with {tag_cls=} {kwargs=}')
                values = [tag_cls(**kwargs)]
            elif value_key == 'text' and isinstance(value_spec, MultiSpec):
                text_values = set(chain.from_iterable(t.text for t in tags.getall(tag_id)))
                text_values.update(map(str, value))
                kwargs['text'] = sorted(text_values)
                log.debug(f'Creating tag with {tag_cls=} {kwargs=}')
                values = [tag_cls(**kwargs)]
            else:
                raise TypeError(f'Unable to add {value=} for {tag=} - {tag_cls=} has {value_key=} ({spec_fields=})')
        log.debug(f'Setting {self}.tags.setall({tag_id=!r}, {value=!r})')
        tags.setall(tag_id, values)

    def _set_mp4_flac_text_tag(self, tag_id: str, value, replace: bool = False):
        tag_type = self.tag_type
        tags = self._f.tags
        if replace:
            if not isinstance(value, list):
                value = [value]
        else:
            existing = set(self.tags_for_id(tag_id))
            if isinstance(value, Collection) and not isinstance(value, str):
                existing.update(value)
            else:
                existing.add(value)
            value = sorted(existing)

        if tag_type == 'flac' and tag_id in ('TRACKNUMBER', 'DISCNUMBER', 'POPM', 'BPM'):
            value = list(map(str, value))
        elif tag_type == 'mp4' and tag_id.startswith('----:'):
            value = [v.encode('utf-8') if isinstance(v, str) else v for v in value]

        log.debug(f'Setting {self}.tags[{tag_id!r}] = {value!r}')
        try:
            tags[tag_id] = value
        except Exception as e:
            log.error(f'Error setting tag={tag_id!r} on {self} to {value=!r}: {e}')
            raise

    def normalize_tag_id(self, tag_name_or_id: str) -> str:
        if type_to_id := TYPED_TAG_MAP.get(tag_name_or_id.lower()):
            try:
                return type_to_id[self.tag_type]
            except KeyError as e:
                raise UnsupportedTagForFileType(tag_name_or_id, self) from e
        id_to_name = tag_id_to_name_map_for_type(self.tag_type)
        if tag_name_or_id in id_to_name:
            return tag_name_or_id
        id_upper = tag_name_or_id.upper()
        if id_upper in id_to_name:
            return id_upper
        if self.tag_type == 'mp3':
            if id_upper in Frames:
                return id_upper
            elif (prefix := id_upper.split(':', 1)[0]) and prefix in Frames:
                return tag_name_or_id if prefix in ('TXXX', 'WXXX') else prefix
            raise InvalidTagName(id_upper, self)
        else:
            return tag_name_or_id

    def normalize_tag_name(self, tag_name_or_id: str) -> str:
        if tag_name_or_id in TYPED_TAG_MAP:
            return tag_name_or_id
        id_lower = tag_name_or_id.lower()
        if id_lower in TYPED_TAG_MAP:
            return id_lower
        id_to_name = tag_id_to_name_map_for_type(self.tag_type)
        for val in (tag_name_or_id, id_lower, tag_name_or_id.upper()):
            if name := id_to_name.get(val):
                return name
        return tag_name_or_id

    def _get_tag_display_name(self, tag_id: str, tag_name: str = None):
        disp_name_map = TYPED_TAG_DISPLAY_NAME_MAP[self.tag_type]
        for func in (str, str.lower, str.upper):
            try:
                return disp_name_map[tag_id if func is str else func(tag_id)]
            except KeyError:
                pass
        if self.tag_type == 'mp3' and len(tag_id) > 4:
            trunc_id = tag_id[:4]
            for func in (str, str.upper):
                try:
                    return disp_name_map[trunc_id if func is str else func(trunc_id)]
                except KeyError:
                    pass
        tag_name = tag_name or self.normalize_tag_name(tag_id)
        for func in (str, str.lower):
            try:
                return TAG_NAME_DISPLAY_NAME_MAP[tag_name if func is str else func(tag_name)]
            except KeyError:
                pass
        return tag_name

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
            return self._f.tags.getall(tag_id.upper())      # all MP3 tags are uppercase; some MP4 tags are mixed case
        return self._f.tags.get(tag_id, [])                 # MP4Tags doesn't have getall() and always returns a list

    def tags_for_name(self, tag_name: str):
        """
        :param str tag_name: A tag name; see :meth:`.tag_name_to_id` for mapping of names to IDs
        :return list: All tags from this file with the given name
        """
        return self.tags_for_id(self.normalize_tag_id(tag_name))

    def get_tag(self, tag: str, by_id: bool = False):
        """
        :param str tag: The name of the tag to retrieve, or the tag ID if by_id is set to True
        :param bool by_id: The provided value was a tag ID rather than a tag name
        :return: The tag object if there was a single instance of the tag with the given name/ID
        :raises: :class:`TagValueException` if multiple tags were found with the given name/ID
        :raises: :class:`TagNotFound` if no tags were found with the given name/ID
        """
        tags = self.tags_for_id(tag) if by_id else self.tags_for_name(tag)
        if len(tags) > 1:
            fmt = 'Multiple {!r} tags found for {}: {}'
            raise TagValueException(fmt.format(tag, self, ', '.join(map(repr, tags))))
        elif not tags:
            raise TagNotFound(f'No {tag!r} tags were found for {self}')
        return tags[0]

    def get_tag_values(self, tag: str, strip: bool = True, by_id: bool = False, default=_NotSet):
        tags = self.tags_for_id(tag) if by_id else self.tags_for_name(tag)
        if not tags:
            if default is not _NotSet:
                return [default]
            raise TagNotFound(f'No {tag!r} tags were found for {self}')

        if values := self._normalize_values(tags, strip):
            return values
        elif default is not _NotSet:
            return [default]
        raise TagNotFound(f'No {tag!r} tag values were found for {self}')

    def _normalize_values(self, values, strip: bool = True):
        if isinstance(values, bool):
            return [values]
        elif self.tag_type == 'mp3':
            if not isinstance(values, list):
                values = [values]
            vals = []
            for tag_obj in values:
                try:
                    text = tag_obj.text
                except AttributeError:
                    if isinstance(tag_obj, POPM):
                        vals.append(tag_obj.rating)  # noqa
                    else:
                        vals.append(tag_obj)
                else:
                    if isinstance(text, str):
                        vals.append(text)  # The text attr for USLT/Lyrics is a string, while most others are a list
                    else:
                        vals.extend(text)
        elif self.tag_type == 'mp4':
            vals = []
            for value in values:
                if isinstance(value, MP4FreeForm):
                    if encoding := MP4_STR_ENCODINGS.get(value.dataformat):
                        vals.append(value.decode(encoding))
                    else:
                        raise ValueError(f'Unexpected MP4FreeForm {value=} in {self}')
                else:
                    vals.append(value)
        else:
            vals = values

        normalized = filter(None, vals)
        if strip:
            return [value.strip() if isinstance(value, str) else value for value in normalized]
        else:
            return list(normalized)

    def get_tag_value_or_values(self, tag: str, strip: bool = True, by_id: bool = False, default=_NotSet):
        values = self.get_tag_values(tag, strip, by_id, default)
        if isinstance(values, list) and len(values) == 1 and tag.upper() not in ('\xa9GEN', 'TCON', 'GENRE'):
            return values[0]
        return values

    def tag_text(self, tag: str, strip: bool = True, by_id: bool = False, default=_NotSet):
        """
        :param str tag: The name of the tag to retrieve, or the tag ID if by_id is set to True
        :param bool strip: Strip leading/trailing spaces from the value before returning it
        :param bool by_id: The provided value was a tag ID rather than a tag name
        :param None|Str default: Default value to return when a TagValueException would otherwise be raised
        :return str: The text content of the tag with the given name if there was a single value
        :raises: :class:`TagValueException` if multiple values existed for the given tag
        """
        try:
            values = self.get_tag_values(tag, strip=strip, by_id=by_id)
        except TagNotFound:
            if default is not _NotSet:
                return default
            raise
        return ';'.join(map(str, values))

    def all_tag_text(self, tag_name: str, suppress_exc: bool = True):
        try:
            for tag in self.tags_for_name(tag_name):
                yield from tag
        except KeyError as e:
            if suppress_exc:
                log.debug('{} has no {} tags - {}'.format(self, tag_name, e))
            else:
                raise e

    def iter_clean_tags(self) -> Iterator[tuple[str, str, Any]]:
        mp3 = self.tag_type == 'mp3'
        for tag, value in self._f.tags.items():
            _tag = tag[:4] if mp3 else tag
            yield _tag, self.normalize_tag_name(_tag), value

    def iter_tag_id_name_values(self) -> Iterator[tuple[str, str, str, str, Any]]:
        mp3 = self.tag_type == 'mp3'
        for tag_id, value in self._f.tags.items():
            disp_name = self._get_tag_display_name(tag_id)
            trunc_id = tag_id[:4] if mp3 else tag_id
            tag_name = self.normalize_tag_name(tag_id)
            log.debug(f'Processing values for {tag_name=} {tag_id=} {value=} on {self}')
            if values := self._normalize_values(value):
                if isinstance(values, list) and len(values) == 1 and disp_name != 'Genre':
                    values = values[0]
                yield trunc_id, tag_id, tag_name, disp_name, values

    # endregion

    # region Tag-Related Properties
    @cached_property
    def all_artists(self) -> set[Name]:
        return self.album_artists.union(self.artists)

    @cached_property
    def album_artists(self) -> set[Name]:
        if album_artist := self.tag_album_artist:
            return set(split_artists(album_artist))
        return set()

    @cached_property
    def artists(self) -> set[Name]:
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
        # TODO: Do without the cast/parse from string
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
        # TODO: Do without the cast/parse from string
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
    def star_rating_10(self) -> Optional[int]:
        if (rating := self.rating) is not None:
            return stars_from_256(rating, 10)
        return None

    @star_rating_10.setter
    def star_rating_10(self, value: Union[int, float]):
        self.rating = stars_to_256(value, 10)

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
        self.rating = stars_to_256(value, 5)

    # endregion

    def tagless_sha256sum(self):
        with self.path.open('rb') as f:
            tmp = BytesIO(f.read())

        try:
            File(tmp).tags.delete(tmp)
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
        for lyric_tag in self.tags_for_name('lyrics'):
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
                from .bpm import get_bpm
                if not (bpm := self._bpm):
                    bpm = self._bpm = get_bpm(self.path, self.sample_rate)
                if save:
                    self.set_text_tag('bpm', bpm)
                    log.debug(f'Saving {bpm=} for {self}')
                    self.save()
            else:
                bpm = None
        return bpm

    def update_tags(self, name_value_map, dry_run=False, no_log=None, none_level=19, add_genre=False):
        """
        :param dict name_value_map: Mapping of {tag name: new value}
        :param bool dry_run: Whether tags should actually be updated
        :param container no_log: Names of tags for which updates should not be logged
        :param int none_level: If no changes need to be made, the log level for the message stating that.
        :param bool add_genre: Add any specified genres instead of replacing them
        """
        no_log = no_log or ()
        to_log = {}
        to_update = {}
        for tag_name, new_value in sorted(name_value_map.items()):
            file_val = self.tag_text(tag_name, default=None)
            cmp_val = str(new_value) if tag_name in ('disk', 'track', 'rating') else new_value
            if tag_name == 'genre':  # TODO: Check value case?
                new_vals = {new_value} if isinstance(new_value, str) else set(new_value)
                file_vals = set(self.tag_genres)
                if (add_genre and not file_vals.issuperset(new_vals)) or (not add_genre and new_vals != file_vals):
                    to_update[tag_name] = (file_val, new_value)
                    if tag_name not in no_log:
                        new_to_log = sorted(file_vals.union(new_vals) if add_genre else new_vals)
                        to_log[tag_name] = (sorted(file_vals), new_to_log)
            elif cmp_val != file_val:
                to_update[tag_name] = (file_val, new_value)
                if tag_name not in no_log:
                    to_log[tag_name] = (file_val, new_value)

            # if add_genre and tag_name == 'genre':
            #     # TODO: Check value case?
            #     new_vals = {new_value} if isinstance(new_value, str) else set(new_value)
            #     file_vals = set(self.tag_genres)
            #     if not file_vals.issuperset(new_vals):
            #         to_update[tag_name] = (file_val, new_value)
            #         if tag_name not in no_log:
            #             to_log[tag_name] = (file_val, ';'.join(sorted(file_vals.union(new_vals))))
            #
            # elif cmp_val != file_val:
            #     if tag_name == 'genre':
            #         new_vals = {new_value} if isinstance(new_value, str) else set(new_value)
            #         file_vals = set(self.tag_genres)
            #         if new_vals == file_vals:
            #             continue
            #
            #     to_update[tag_name] = (file_val, new_value)
            #     if tag_name not in no_log:
            #         to_log[tag_name] = (file_val, new_value)

        if to_update:
            from ..changes import print_tag_changes
            if to_log:
                print_tag_changes(self, to_log, dry_run)

            do_save = True
            for tag_name, (file_val, new_value) in to_update.items():
                if not dry_run:
                    replace = not (add_genre and tag_name == 'genre')
                    log.log(9, f'Calling {self!r}.set_text_tag({tag_name=!r}, {new_value=!r}, {replace=!r})')
                    try:
                        self.set_text_tag(tag_name, new_value, by_id=False, replace=replace)
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
            if not (tag_name := MP3_TAG_DISPLAY_NAME_MAP.get(tag_id)):
                raise ValueError(f'Invalid tag ID: {tag_id}')
            norm_name = self.normalize_tag_name(tag_id)

            if current_vals := self.tags_for_id(tag_id):
                if len(current_vals) > 1:
                    log.warning(f'Found multiple values for {tag_id}/{tag_name} in {self} - using first value')

                current_val = current_vals[0]
                if tag_id.startswith('WXXX:'):
                    current_text = current_val.url[0]
                else:
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

    def get_cover_tag(self):
        if self.tag_type == 'flac':
            try:
                return self._f.pictures[0]
            except IndexError:
                return None
        else:
            return self.get_tag('cover')

    def get_cover_data(self) -> tuple[bytes, str]:
        if (cover := self.get_cover_tag()) is None:
            raise TagNotFound(f'{self} has no album cover')
        if self.tag_type in ('mp3', 'flac'):
            mime = cover.mime.split('/')[-1].lower()
            ext = 'jpg' if mime in ('jpg', 'jpeg') else mime
            return cover.data, ext
        elif self.tag_type == 'mp4':
            ext = 'jpg' if cover.imageformat == MP4Cover.FORMAT_JPEG else 'png'
            return cover, ext
        else:
            raise TypeError(f'{self} has unexpected type={self.tag_type!r} for album cover extraction')

    def get_cover_image(self, extras: bool = False) -> Union['Image.Image', tuple['Image.Image', bytes, str]]:
        from PIL import Image

        data, ext = self.get_cover_data()
        image = Image.open(BytesIO(data))
        return (image, data, ext) if extras else image

    def del_cover_tag(self, save: bool = False, dry_run: bool = False):
        prefix = '[DRY RUN] Would remove' if dry_run else 'Removing'
        log.info(f'{prefix} tags from {self}: cover')
        if not dry_run:
            if self.tag_type == 'flac':
                self._f.clear_pictures()
            else:
                self.delete_tag(self.normalize_tag_id('cover'))
            if save:
                self.save()

    def _log_cover_changes(self, current: list[ImageTag], cover: ImageTag, dry_run: bool):
        if current:
            del_prefix = '[DRY RUN] Would remove' if dry_run else 'Removing'
            log.info(f'{del_prefix} existing image(s) from {self}: {current}')

        set_prefix = '[DRY RUN] Would add' if dry_run else 'Adding'
        size = len(cover) if self.tag_type == 'mp4' else len(cover.data)
        log.info(f'{set_prefix} cover image to {self}: [{readable_bytes(size)}] {cover!r}')
        return not dry_run

    def set_cover_data(self, image: 'Image.Image', dry_run: bool = False, max_width: int = 1200):
        image, data, mime_type = prepare_cover_image(image, self.tag_type, max_width)
        self._set_cover_data(image, data, mime_type, dry_run)

    def _set_cover_data(self, image: 'Image.Image', data: bytes, mime_type: str, dry_run: bool = False):
        if self.tag_type == 'mp3':
            current = self._f.tags.getall('APIC')
            cover = APIC(mime=mime_type, type=PictureType.COVER_FRONT, data=data)  # noqa
            if self._log_cover_changes(current, cover, dry_run):
                self._f.tags.delall('APIC')
                self._f.tags[cover.HashKey] = cover
        elif self.tag_type == 'mp4':
            current = self._f.tags['covr']
            try:
                cover_fmt = MP4_MIME_FORMAT_MAP[mime_type]
            except KeyError as e:
                raise ValueError(f'Invalid {mime_type=} for {self!r} - must be JPEG or PNG for MP4 cover images') from e
            cover = MP4Cover(data, cover_fmt)
            if self._log_cover_changes(current, cover, dry_run):
                self._f.tags['covr'] = [cover]
        elif self.tag_type == 'flac':
            current = self._f.pictures
            cover = Picture()
            cover.type = PictureType.COVER_FRONT  # noqa
            cover.mime = mime_type
            cover.width, cover.height = image.size
            cover.depth = 1 if image.mode == '1' else 32 if image.mode in ('I', 'F') else 8 * len(image.getbands())
            cover.data = data
            if self._log_cover_changes(current, cover, dry_run):
                self._f.clear_pictures()
                self._f.add_picture(cover)

        if not dry_run:
            self.save()


def iter_music_files(paths: Paths) -> Iterator[SongFile]:
    non_music_exts = {'jpg', 'jpeg', 'png', 'jfif', 'part', 'pdf', 'zip', 'webp'}
    for file_path in iter_files(paths):
        music_file = SongFile(file_path)
        if music_file:
            yield music_file
        else:
            if file_path.suffix not in non_music_exts:
                log.log(5, f'Not a music file: {file_path}')


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
