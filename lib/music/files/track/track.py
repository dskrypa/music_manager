"""
Song File / Audio Track

:author: Doug Skrypa
"""

from __future__ import annotations

import logging
import struct
from base64 import b64decode, b64encode
from collections import Counter
from datetime import date
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Optional, Union, Iterator, Any, Collection, Type, Mapping, TypeVar, Callable
from urllib.parse import quote
from weakref import WeakValueDictionary

from mutagen import File, FileType
from mutagen.flac import FLAC, Picture
from mutagen.id3 import ID3, POPM, TDRC, Frames, Frame, _frames, ID3FileType, APIC, PictureType, Encoding
from mutagen.id3._specs import MultiSpec, Spec
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4, MP4Cover, AtomDataType, MP4FreeForm
from mutagen.ogg import OggFileType, OggPage
from mutagen.oggflac import OggFLAC
from mutagen.oggvorbis import OggVorbis
from mutagen.oggopus import OggOpus
from mutagen.wave import WAVE, _WaveID3

from ds_tools.caching.decorators import cached_property, ClearableCachedPropertyMixin
from ds_tools.core.decorate import cached_classproperty
from ds_tools.core.patterns import PatternMatcher, FnMatcher, ReMatcher
from ds_tools.fs.paths import iter_files
from ds_tools.output.formatting import readable_bytes
from ds_tools.output.prefix import LoggingPrefix

from music.common.ratings import stars_to_256, stars_from_256, stars
from music.common.utils import format_duration
from music.constants import TYPED_TAG_MAP, TYPED_TAG_DISPLAY_NAME_MAP, TAG_NAME_DISPLAY_NAME_MAP
from music.text.name import Name
from ..cover import prepare_cover_image, bytes_to_image
from ..exceptions import InvalidTagName, TagException, TagNotFound, TagValueException, UnsupportedTagForFileType
from ..exceptions import InvalidAlbumDir
from ..parsing import split_artists, AlbumName
from ..paths import ON_WINDOWS, FileBasedObject, plex_track_path
from .descriptors import MusicFileProperty, TextTagProperty, TagValuesProperty, _NotSet
from .patterns import StrsOrPatterns, SAMPLE_RATE_PAT, cleanup_lyrics, glob_patterns, cleanup_album_name
from .utils import tag_repr, parse_file_date, tag_id_to_name_map_for_type

if TYPE_CHECKING:
    from PIL.Image import Image as PILImage
    from plexapi.audio import Track
    from music.typing import PathLike, OptStr, OptInt, Bool, StrIter
    from ds_tools.fs.typing import Paths
    from ..album import AlbumDir
    from ..typing import MutagenFile, ImageTag, TagsType, ID3Tag, TagChanges

__all__ = ['SongFile', 'iter_music_files']
log = logging.getLogger(__name__)

MP4_STR_ENCODINGS = {AtomDataType.UTF8: 'utf-8', AtomDataType.UTF16: 'utf-16be'}  # noqa
MP4_MIME_FORMAT_MAP = {'image/jpeg': MP4Cover.FORMAT_JPEG, 'image/png': MP4Cover.FORMAT_PNG}

T = TypeVar('T')


class SongFile(ClearableCachedPropertyMixin, FileBasedObject):
    """Adds some properties/methods to mutagen.File types that facilitate other functions"""
    # region Class Attributes
    tag_type: OptStr = None
    file_type: OptStr = None
    __ft_cls_map = {}
    __instances: dict[Path, SongFile] = WeakValueDictionary()
    # endregion
    # region Instance Attributes + File/Tag Properties
    _bpm: OptInt = None
    _f: Optional[MutagenFile] = None
    _path: Optional[Path] = None
    tags: TagsType              = MusicFileProperty('tags')
    filename: str               = MusicFileProperty('filename')
    length: float               = MusicFileProperty('info.length')  # length of this song in seconds
    channels: int               = MusicFileProperty('info.channels')
    bits_per_sample: int        = MusicFileProperty('info.bits_per_sample')
    _bitrate: int               = MusicFileProperty('info.bitrate')
    _sample_rate: int           = MusicFileProperty('info.sample_rate')
    tag_artist: OptStr          = TextTagProperty('artist', default=None)
    tag_album_artist: OptStr    = TextTagProperty('album_artist', default=None)
    tag_title: OptStr           = TextTagProperty('title', default=None)
    tag_album: OptStr           = TextTagProperty('album', default=None)
    tag_album_title: OptStr     = TextTagProperty('album_title', default=None)  # Non-standard, low frequency of use
    tag_genre: OptStr           = TextTagProperty('genre', default=None)
    tag_genres: list[str]       = TagValuesProperty('genre', default=None)
    date: Optional[date]        = TextTagProperty('date', parse_file_date, default=None)
    album_url: OptStr           = TextTagProperty('wiki:album', default=None)
    artist_url: OptStr          = TextTagProperty('wiki:artist', default=None)
    rating: OptInt              = TextTagProperty('rating', int, default=None, save=True)
    # endregion

    def __init_subclass__(cls, ft_classes: Collection[Type[FileType]] = (), **kwargs):
        super().__init_subclass__(**kwargs)
        for c in ft_classes:
            cls.__ft_cls_map[c] = cls

    # region Constructors

    def __new__(cls, file_path: PathLike, *args, options=_NotSet, **kwargs):
        file_path = Path(file_path).expanduser().resolve() if isinstance(file_path, str) else file_path
        try:
            return cls.__instances[file_path]
        except KeyError:
            if (music_file := cls._new_file(file_path, *args, options=options, **kwargs)) is not None:
                mf_cls: Type[SongFile] = cls.__ft_cls_map.get(type(music_file), cls)
                # print(f'Found {mf_cls=} for {type(music_file)=}')
                obj = super().__new__(mf_cls)
            else:
                return None
                # print(f'No file initialized for {file_path=}')
                # obj = super().__new__(cls)
            obj._init(music_file, file_path)
            cls.__instances[file_path] = obj
            return obj

    @classmethod
    def _new_file(cls, file_path: PathLike, *args, options=_NotSet, **kwargs):
        if options is _NotSet:  # note: webm is not supported by mutagen
            options = (MP3, FLAC, MP4, ID3FileType, WAVE, OggFLAC, OggVorbis, OggOpus)
        ipod = hasattr(file_path, '_ipod')
        filething = file_path.open('rb') if ipod else file_path
        error = True
        try:
            music_file = File(filething, *args, options=options, **kwargs)
        except Exception as e:
            log.debug(f'Error loading {file_path}: {e}')
            return None
        else:
            if music_file is None:  # mutagen.File is a function that returns different obj types based on the
                return None  # given file path - it may return None
            error = False
        finally:
            if error and ipod:
                filething.close()

        return music_file

    def __init__(self, file_path: PathLike, *args, **kwargs):
        if not getattr(self, '_SongFile__initialized', False):
            self._album_dir = None
            self._in_album_dir = False
            self.__initialized = True

    @classmethod
    def for_plex_track(cls, track_or_rel_path: Union[Track, str], root: Union[str, Path]) -> SongFile:
        return cls(plex_track_path(track_or_rel_path, root))

    # endregion

    @cached_property
    def album_dir(self) -> AlbumDir | None:
        from ..album import AlbumDir

        if album_dir := self._album_dir is not None:
            return album_dir
        try:
            return AlbumDir(self.path.parent)
        except InvalidAlbumDir:
            pass
        return None

    # region Internal Methods

    @cached_classproperty
    def _rm_tag_matcher(cls) -> PatternMatcher:  # noqa
        return FnMatcher(())

    def _init(self, mutagen_file: MutagenFile, path: Path):
        self._f = mutagen_file
        self._path = path

    def __getitem__(self, item: str):
        return self._f[item]

    def __getnewargs__(self):
        return (self.path.as_posix(),)

    def __getstate__(self):
        return None  # prevents calling __setstate__ on unpickle; simpler for rebuilt obj to re-calculate cached attrs

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__}({self.rel_path!r})>'

    def __hash__(self) -> int:
        return hash(self.__class__) ^ hash(self.path)

    def __eq__(self, other: SongFile) -> bool:
        return self.path == other.path

    def __lt__(self, other: SongFile) -> bool:
        return self.path_str < other.path_str

    @cached_property
    def extended_repr(self) -> str:
        try:
            info = f'[{self.tag_title!r} by {self.tag_artist}, in {self.album_name_cleaned!r}]'
        except Exception:  # noqa
            info = ''
        return f'<{self.__class__.__name__}({self.rel_path!r}){info}>'

    # endregion

    # region Path & Save

    @property
    def path(self) -> Path:
        return self._path

    @cached_property
    def path_str(self) -> str:
        return self.path.as_posix()

    def rename(self, dest_path: PathLike):
        old_path = self.path
        if not isinstance(dest_path, Path):
            dest_path = Path(dest_path)

        dest_name = dest_path.name                      # on Windows, if the new path is only different by case,
        dest_path = dest_path.expanduser().resolve()    # .resolve() discards the new case, so storing the name first
        dest_path = dest_path.with_name(dest_name)      # and replacing it afterwards preserves the new file name.

        if not dest_path.parent.exists():
            dest_path.parent.mkdir(parents=True, exist_ok=True)

        if self._should_use_temp_file_to_rename(dest_path, dest_name):
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

    def _should_use_temp_file_to_rename(self, dest_path: Path, dest_name: str) -> bool:
        if not dest_path.exists():
            return False
        elif dest_path.samefile(self.path) and ON_WINDOWS and dest_name != self.path.name:
            return True
        raise ValueError(f'Destination for {self} already exists: {dest_path.as_posix()!r}')

    def save(self):
        self._f.tags.save(self._f.filename)

    # endregion

    # region Metadata

    @cached_property
    def length_str(self) -> str:
        """The length of this song in the format (HH:M)M:SS"""
        length = format_duration(int(self._f.info.length))  # Most other programs seem to floor the seconds
        if length.startswith('00:'):
            length = length[3:]
        if length.startswith('0'):
            length = length[1:]
        return length

    @cached_property
    def tag_version(self) -> str:
        try:
            tags = self._f.tags
        except AttributeError:
            tags = None
        if tags is None:
            return '[no tags]'
        else:
            return tags.__name__

    @cached_property
    def bitrate(self) -> int:
        # Bitrate is variable for lossless formats, so the reported value will be an average
        # bit_rate = file_info.sample_rate * file_info.bits_per_sample * file_info.channels  # not accurate for VBR
        info = self._f.info
        try:
            return info.bitrate
        except AttributeError:
            if self.file_type != 'ogg':
                raise

        with self.path.open('rb') as f:
            while (page := OggPage(f)).position == 0:
                pass
            f.seek(0, 2)  # End of the file
            return int((f.tell() - page.offset) * 8 / info.length)

    @cached_property
    def sample_rate(self) -> int:
        # total_samples = file_info.sample_rate * file_info.length
        file = self._f
        info = file.info
        try:
            return info.sample_rate
        except AttributeError:
            if not isinstance(file, OggOpus):
                raise
        with self.path.open('rb') as f:
            while not (page := OggPage(f)).packets[0].startswith(b'OpusHead'):
                pass
            return struct.unpack('<I', page.packets[0][12:16])[0]

    @cached_property
    def sample_rate_khz(self) -> float:
        return self.sample_rate / 1000

    @property
    def lossless(self) -> bool:
        return False

    @cached_property
    def info(self) -> dict[str, Union[str, int, float, bool]]:
        file_info = self._f.info
        file_type = self.file_type
        size = self.path.stat().st_size
        info = {
            'bitrate': self.bitrate,            'bitrate_str': f'{self.bitrate // 1000} Kbps',
            'sample_rate': self.sample_rate,    'sample_rate_str': f'{self.sample_rate:,d} Hz',
            'length': file_info.length,         'length_str': self.length_str,
            'size': size,                       'size_str': readable_bytes(size),
            'lossless': self.lossless,
            'channels': file_info.channels,
            'bits_per_sample': getattr(file_info, 'bits_per_sample', None),
        }
        if file_type == 'mp3':
            info['bitrate_str'] += f' ({str(file_info.bitrate_mode)[12:]})'
            if encoder_info := file_info.encoder_info:
                info['encoder'] = encoder_info
        elif file_type == 'mp4':
            codec = file_info.codec
            info['codec'] = codec if codec == 'alac' else f'{codec} ({file_info.codec_description})'
        elif file_type == 'ogg':
            info['codec'] = self.tag_version[4:-1]
        return info

    def info_summary(self) -> str:
        info = self.info
        lossless = ' [lossless]' if info['lossless'] else ''
        return (
            f'{self.tag_version}{lossless} @ {info["bitrate_str"]}'
            f' ({self.sample_rate/1000} kHz @ {self.bits_per_sample}b/sample)'
            f' {info["length_str"]} / {info["size_str"]}'
        )

    # endregion

    # region Input Normalization

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

        if self.tag_type == 'id3':
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

        if self.tag_type == 'id3' and len(tag_id) > 4:
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

    # endregion

    # region Tag Removal

    def delete_tag(self, tag_id: str, save: bool = False):
        # TODO: When multiple values exist for the tag, make it possible to delete a specific index/value?
        self._delete_tag(tag_id)
        if save:
            self.save()

    def _delete_tag(self, tag_id: str):
        raise TypeError(f'Cannot delete tag_id={tag_id!r} for {self} because its tag type={self.tag_type!r}')

    def remove_all_tags(self, dry_run: Bool = False):
        log.info(f'{LoggingPrefix(dry_run).remove} ALL tags from {self}')
        if not dry_run:
            self._f.tags.delete(self._f.filename)

    def remove_tags(self, tag_ids: StrIter, dry_run: Bool = False, log_lvl: int = logging.DEBUG) -> bool:
        tag_ids = list(map(self.normalize_tag_id, tag_ids))
        to_remove = {
            tag_id: val if isinstance(val, list) else [val]
            for tag_id in sorted(tag_ids) if (val := self.tags.get(tag_id) or self.tags_for_id(tag_id))
        }
        if not to_remove:
            log.log(log_lvl, f'{self}: Did not have the tags specified for removal')
            return False

        info_str = ', '.join(f'{tag_id} ({len(vals)})' for tag_id, vals in to_remove.items())
        log.info(f'{LoggingPrefix(dry_run).remove} tags from {self}: {info_str}')

        rm_reprs = {tag_id: Counter(tag_repr(val) for val in vals) for tag_id, vals in to_remove.items()}
        rm_str = '; '.join(
            f'{tag_id}: ' + ', '.join(f'{v} x{c}' if c > 1 else v for v, c in val_reprs.items())
            for tag_id, val_reprs in rm_reprs.items()
        )
        # rm_str = ', '.join(f'{tag_id}: {tag_repr(val)}' for tag_id, vals in to_remove.items() for val in vals)
        log.debug(f'\t{self}: {rm_str}')
        if not dry_run:
            for tag_id in to_remove:
                self.delete_tag(tag_id)
            self.save()
        return True

    # endregion

    # region Tag Update / Addition

    def set_text_tag(self, tag: str, value, by_id: bool = False, replace: bool = True, save: bool = False):
        tag_id = tag if by_id else self.normalize_tag_id(tag)
        self._set_text_tag(tag, tag_id, value, replace)
        if save:
            self.save()

    def _set_text_tag(self, tag: str, tag_id: str, value, replace: bool = True):
        if (tag_type := self.tag_type) not in ('mp4', 'vorbis'):
            raise TypeError(f'Unable to set {tag!r} for {self} because its extension is {tag_type!r}')

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

        if tag_type == 'vorbis' and tag_id in ('TRACKNUMBER', 'DISCNUMBER', 'POPM', 'BPM'):
            value = list(map(str, value))
        elif tag_type == 'mp4' and tag_id.startswith('----:'):
            value = [v.encode('utf-8') if isinstance(v, str) else v for v in value]

        log.debug(f'Setting {self}.tags[{tag_id!r}] = {value!r}')
        try:
            tags[tag_id] = value
        except Exception as e:
            log.error(f'Error setting tag={tag_id!r} on {self} to {value=}: {e}')
            raise

    # endregion

    # region Get Tag Values

    def tags_for_id(self, tag_id: str):
        """
        :param str tag_id: A tag ID
        :return list: All tags from this file with the given ID
        """
        try:
            return self._f.tags.get(tag_id, [])  # MP4Tags doesn't have getall() and always returns a list
        except AttributeError:
            log.warning(f'No tags found for {self.path}')
            raise

    def tags_for_name(self, tag_name: str):
        """
        :param str tag_name: A tag name; see :meth:`.tag_name_to_id` for mapping of names to IDs
        :return list: All tags from this file with the given name
        """
        return self.tags_for_id(self.normalize_tag_id(tag_name))

    def _get_tags(self, tag: str, by_id: Bool = False):
        if by_id:
            return self.tags_for_id(tag)
        else:
            return self.tags_for_name(tag)

    def get_tag(self, tag: str, by_id: Bool = False):
        """
        :param tag: The name of the tag to retrieve, or the tag ID if by_id is set to True
        :param by_id: The provided value was a tag ID rather than a tag name
        :return: The tag object if there was a single instance of the tag with the given name/ID
        :raises: :class:`TagValueException` if multiple tags were found with the given name/ID
        :raises: :class:`TagNotFound` if no tags were found with the given name/ID
        """
        tags = self._get_tags(tag, by_id)
        if len(tags) > 1:
            raise TagValueException(f'Multiple {tag!r} tags found for {self}: ' + ', '.join(map(repr, tags)))
        elif not tags:
            raise TagNotFound(f'No {tag!r} tags were found for {self}')
        return tags[0]

    def get_tag_values(self, tag: str, strip: bool = True, by_id: Bool = False, default=_NotSet):
        if not (tags := self._get_tags(tag, by_id)):
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

        normalized = filter(None, self._normalize_tag_values(values))
        if strip:
            return [value.strip() if isinstance(value, str) else value for value in normalized]
        else:
            return list(normalized)

    def _normalize_tag_values(self, values):
        return values

    def get_tag_value_or_values(self, tag: str, strip: bool = True, by_id: Bool = False, default=_NotSet):
        values = self.get_tag_values(tag, strip, by_id, default)
        if isinstance(values, list) and len(values) == 1 and tag.upper() not in ('\xa9GEN', 'TCON', 'GENRE'):
            return values[0]
        return values

    def tag_text(self, tag: str, strip: bool = True, by_id: Bool = False, default: T = _NotSet) -> str | T:
        """
        :param tag: The name of the tag to retrieve, or the tag ID if by_id is set to True
        :param strip: Strip leading/trailing spaces from the value before returning it
        :param by_id: The provided value was a tag ID rather than a tag name
        :param default: Default value to return when a TagValueException would otherwise be raised
        :return: The text content of the tag with the given name if there was a single value
        :raises: :class:`TagValueException` if multiple values existed for the given tag
        """
        try:
            values = self.get_tag_values(tag, strip=strip, by_id=by_id)
        except (TagNotFound, UnsupportedTagForFileType):
            if default is _NotSet:
                raise
            return default
        return ';'.join(map(str, values))

    def _iter_tags(self) -> Iterator[tuple[str, Any]]:
        try:
            yield from self._f.tags.items()
        except AttributeError:
            return

    def iter_clean_tags(self) -> Iterator[tuple[str, str, Any]]:
        for tag, value in self._iter_tags():
            yield tag, self.normalize_tag_name(tag), value

    def iter_tag_id_name_values(self) -> Iterator[tuple[str, str, str, str, Any]]:
        for tag_id, value in self._iter_tags():
            disp_name = self._get_tag_display_name(tag_id)
            tag_name = self.normalize_tag_name(tag_id)
            # log.debug(f'Processing values for {tag_name=} {tag_id=} {value=} on {self}')
            if values := self._normalize_values(value):
                if isinstance(values, list) and len(values) == 1 and disp_name != 'Genre':
                    values = values[0]
                # tag_id is yielded 2x to be consistent between ID3 and other tag types
                yield tag_id, tag_id, tag_name, disp_name, values

    # endregion

    @property
    def common_tag_info(self) -> dict[str, Union[str, int, float, bool, None]]:
        return {
            'album artist': self.tag_album_artist,
            'artist': self.tag_artist,
            'album': self.tag_album,
            'disk': self.disk_num,
            'track': self.track_num,
            'title': self.tag_title,
            'rating': stars(self.star_rating_10) if self.star_rating_10 is not None else '',
            'genre': self.tag_genre,
            'date': str(self.date) if self.date else None,
            'bpm': self.bpm(calculate=False),
        }

    # region Artist Tag Properties

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
            if (album := self.album_name) and album.feat:
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

    # endregion

    # region Album Name Tag Properties

    @cached_property
    def album_name(self) -> Optional[AlbumName]:
        if album := self.tag_album:
            return AlbumName.parse(album, self.tag_artist)
        return None

    @cached_property
    def album_title_name(self) -> Optional[AlbumName]:
        # Non-standard, but encountered occasionally in the wild
        if album := self.tag_album_title:
            return AlbumName.parse(album, self.tag_artist)
        return None

    @cached_property
    def title_as_album_name(self) -> Optional[AlbumName]:
        # Intended for use for singles with no album name tag
        if title := self.tag_title:
            return AlbumName.parse(title, self.tag_artist)
        return None

    @cached_property
    def album_name_cleaned(self) -> str:
        return cleanup_album_name(self.tag_album, self.tag_artist) or self.tag_album

    @cached_property
    def album_name_cleaned_plus_and_part(self) -> tuple[str, OptStr]:
        """Tuple of title, part"""
        from .patterns import split_album_part

        return split_album_part(self.album_name_cleaned)

    # endregion

    # region Numeric Tag Properties

    @cached_property
    def year(self) -> OptInt:
        try:
            return self.date.year
        except Exception:  # noqa
            return None

    def _num_tag(self, name: str) -> int:
        orig = value = self.tag_text(name, default=None)
        if not value:
            return 0
        if '/' in value:
            value = value.split('/', 1)[0].strip()
        if ',' in value:
            value = value.split(',', 1)[0].strip()
        if value.startswith('('):
            value = value[1:].strip()
        try:
            return int(value)
        except Exception as e:
            log.debug(f'{self}: Error converting {name} num={orig!r} [{value!r}] to int: {e}')
            return 0

    @cached_property
    def track_num(self) -> int:
        return self._num_tag('track')

    @cached_property
    def disk_num(self) -> int:
        return self._num_tag('disk')

    @property
    def star_rating_10(self) -> OptInt:
        if (rating := self.rating) is not None:
            return stars_from_256(rating, 10)
        return None

    @star_rating_10.setter
    def star_rating_10(self, value: Union[int, float]):
        self.rating = stars_to_256(value, 10)

    @property
    def star_rating(self) -> OptInt:
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

    # region Hash / Fingerprint Methods

    def tagless_sha256sum(self) -> str:
        from io import BytesIO

        with self.path.open('rb') as f:
            tmp = BytesIO(f.read())

        try:
            File(tmp).tags.delete(tmp)
        except AttributeError as e:
            log.error('Error determining tagless sha256sum for {}: {}'.format(self._f.filename, e))
            return self._f.filename

        tmp.seek(0)
        return sha256(tmp.read()).hexdigest()

    def sha256sum(self) -> str:
        return sha256(self.path.read_bytes()).hexdigest()

    # @cached_property
    # def acoustid_fingerprint(self):
    #     """Returns the 2-tuple of this file's (duration, fingerprint)"""
    #     return acoustid.fingerprint_file(self.filename)

    # endregion

    # region Tag Cleanup

    def _log_update(self, tag_name: str, orig_val: str, new_val: str, dry_run: Bool):
        lp = LoggingPrefix(dry_run)
        log.info(f'{lp.update} {tag_name} for {self} from {tag_repr(orig_val)!r} to {tag_repr(new_val)!r}')

    def cleanup_title(self, dry_run: Bool = False, only_matching: Bool = False):
        if not (title := self.tag_title):
            log.debug(f'No title found for {self}')
            return

        if m := SAMPLE_RATE_PAT.search(title):
            if only_matching and self.sample_rate_khz != float(m.group(1)):  # title khz
                log.debug(f'Found sample rate={m.group(0)!r} != {self.sample_rate_khz} in title of {self}')
                return
            elif clean_title := SAMPLE_RATE_PAT.sub('', title).strip():
                self._log_update('title', title, clean_title, dry_run)
                if not dry_run:
                    self.set_text_tag('title', clean_title, save=True)
            else:
                log.debug(f'Found sample rate={m.group(0)!r} in title of {self}, but it is the full title')

    def cleanup_lyrics(self, dry_run: Bool = False):
        changes = 0
        is_id3 = self.tag_type == 'id3'
        new_lyrics = []
        for lyric_tag in self.tags_for_name('lyrics'):
            lyric = lyric_tag.text if is_id3 else lyric_tag
            if new_lyric := cleanup_lyrics(lyric):
                self._log_update('lyrics', lyric, new_lyric, dry_run)
                if not dry_run:
                    if is_id3:
                        lyric_tag.text = new_lyric
                    else:
                        new_lyrics.append(new_lyric)
                    changes += 1
            else:
                new_lyrics.append(lyric)

        if changes and not dry_run:
            log.info(f'Saving changes to lyrics in {self}')
            if not is_id3:  # TODO: ...why not?
                self.set_text_tag('lyrics', new_lyrics)
            self.save()

    def fix_song_tags(self, dry_run: Bool = False):
        self.cleanup_title(dry_run)
        self.cleanup_lyrics(dry_run)

    def _get_rm_tag_matcher(self, extras: Collection[str] = None) -> Callable[[str], Bool]:
        rm_tag_matcher: PatternMatcher = self._rm_tag_matcher  # noqa
        pat_match = rm_tag_matcher.match if rm_tag_matcher.patterns else lambda tag: False
        if not extras:
            return pat_match

        extras = set(map(str.lower, extras))

        def pat_or_extra_match(tag_value: str) -> bool:
            if pat_match(tag_value):
                return True
            return tag_value.lower() in extras

        return pat_or_extra_match

    def get_bad_tags(self, extras: Collection[str] = None) -> set[str] | None:
        if (track_tags := self.tags) is None:
            return None
        rm_tag_match = self._get_rm_tag_matcher(extras)
        keep_tags = {'----:com.apple.iTunes:ISRC', '----:com.apple.iTunes:LANGUAGE'}
        return {tag for tag in track_tags if rm_tag_match(tag) and tag not in keep_tags}

    def remove_bad_tags(self, dry_run: Bool = False, extras: Collection[str] = None) -> bool:
        # TODO: Also dedupe tags with multiple instances of the same value
        if to_remove := self.get_bad_tags(extras):
            return self.remove_tags(to_remove, dry_run)
        return False

    # endregion

    # region BPM

    def _get_bpm(self) -> OptInt:
        try:
            return int(self.tag_text('bpm'))
        except (TagException, ValueError):
            return None

    def bpm(self, save: bool = True, calculate: bool = True) -> OptInt:
        """
        :param save: If the BPM was not already stored in a tag, save the calculated BPM in a tag.
        :param calculate: If the BPM was not already stored in a tag, calculate it
        :return: This track's BPM from a tag if available, or calculated
        """
        if bpm := self._get_bpm():
            return bpm
        elif calculate:
            return self._calculate_bpm(save)
        else:
            return bpm

    def _calculate_bpm(self, save: bool = True) -> OptInt:
        from .bpm import get_bpm

        if not (bpm := self._bpm):
            bpm = self._bpm = get_bpm(self.path, self.sample_rate)
        if save:
            self.set_text_tag('bpm', bpm)
            log.debug(f'Saving {bpm=} for {self}')
            self.save()

        return bpm

    def maybe_add_bpm(self, dry_run: Bool = False) -> str:
        if bpm := self._get_bpm():
            level, message = 19, f'{self} already has a value stored for BPM={bpm}'
        else:
            bpm = self._calculate_bpm(not dry_run)
            level, message = 20, f'{LoggingPrefix(dry_run).add} BPM={bpm} to {self}'
        log.log(level, message)
        return message

    # endregion

    # region Tag Updates

    def update_tags(
        self,
        name_value_map: Mapping[str, Any],
        dry_run: bool = False,
        no_log: Collection[str] = None,
        none_level: int = 19,
        add_genre: bool = False,
    ):
        """
        :param name_value_map: Mapping of {tag name: new value}
        :param dry_run: Whether tags should actually be updated
        :param no_log: Names of tags for which updates should not be logged
        :param none_level: If no changes need to be made, the log level for the message stating that.
        :param add_genre: Add any specified genres instead of replacing them
        """
        # log.debug(f'update_tags: {name_value_map=}, {dry_run=}, {add_genre=}')
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

        if to_update:
            self._update_tags(to_update, to_log, dry_run, add_genre)
        else:
            log.log(none_level, f'No changes to make for {self.extended_repr}')

    def _update_tags(self, to_update: TagChanges, to_log: TagChanges, dry_run: bool, add_genre: bool):
        from ..changes import print_tag_changes

        if to_log:
            print_tag_changes(self, to_log, dry_run)

        do_save = True
        for tag_name, (file_val, new_value) in to_update.items():
            if not dry_run:
                replace = not (add_genre and tag_name == 'genre')
                log.log(9, f'Calling {self!r}.set_text_tag({tag_name=}, {new_value=}, {replace=})')
                try:
                    self.set_text_tag(tag_name, new_value, by_id=False, replace=replace)
                except TagException as e:
                    do_save = False
                    log.error(f'Error setting tag={tag_name} on {self}: {e}')

        if do_save and not dry_run:
            self.save()

    def get_tag_updates(
        self,
        tag_ids: StrIter,
        value: str,
        patterns: StrsOrPatterns = None,
        partial: bool = False,
    ):
        if partial and not patterns:
            raise ValueError('Unable to perform partial tag update without any patterns')
        patterns = glob_patterns(patterns)
        to_update = {}
        for tag_id in tag_ids:
            if names_by_type := TYPED_TAG_MAP.get(tag_id):
                tag_id = names_by_type[self.tag_type]

            norm_name = self.normalize_tag_name(tag_id)
            if file_val := self.tag_text(tag_id, default=None):
                new_text = file_val
                if partial:
                    for pat in patterns:
                        new_text = pat.sub(value, new_text)
                else:
                    if patterns:
                        if any(pat.search(file_val) for pat in patterns):
                            new_text = value
                    else:
                        new_text = value

                if new_text != file_val:
                    to_update[norm_name] = new_text
            else:
                to_update[norm_name] = value

            # if current_vals := self.tags_for_id(tag_id):
            #     if len(current_vals) > 1:
            #         log.warning(f'Found multiple values for {tag_id}/{norm_name} in {self} - using first value')
            #
            #     current_val = current_vals[0]
            #     if tag_id.startswith('WXXX:'):
            #         current_text = current_val.url[0]
            #     else:
            #         current_text = current_val.text[0]
            #
            #     new_text = current_text
            #     if partial:
            #         for pat in patterns:
            #             new_text = pat.sub(value, new_text)
            #     else:
            #         if patterns:
            #             if any(pat.search(current_text) for pat in patterns):
            #                 new_text = value
            #         else:
            #             new_text = value
            #
            #     if new_text != current_text:
            #         to_update[norm_name] = new_text
            # else:
            #     to_update[norm_name] = value

        return to_update

    def update_tags_with_value(self, tag_ids, value, patterns=None, partial=False, dry_run=False):
        updates = self.get_tag_updates(tag_ids, value, patterns, partial)
        self.update_tags(updates, dry_run)

    # endregion

    # region Cover Image Methods

    def get_cover_tag(self):
        # TODO: Handle front+back (return front, log the fact that a back cover was found?):
        """
        music.files.exceptions.TagValueException: Multiple 'cover' tags found for <WavFile("...wav")>:
        APIC(encoding=<Encoding.LATIN1: 0>, mime='image/jpeg', type=<PictureType.COVER_FRONT: 3>, desc='', data=b'...'),
        APIC(encoding=<Encoding.LATIN1: 0>, mime='image/jpeg', type=<PictureType.COVER_BACK: 4>, desc=' ', data=b'...')
        """
        return self.get_tag('cover')

    def get_cover_data(self) -> tuple[bytes, str]:
        """Returns a tuple containing the raw cover data bytes, and the image type as a file extension"""
        if self.tag_type not in ('id3', 'vorbis'):
            raise TypeError(f'{self} has unexpected type={self.tag_type!r} for album cover extraction')
        elif (cover := self.get_cover_tag()) is None:
            raise TagNotFound(f'{self} has no album cover')
        mime = cover.mime.split('/')[-1].lower()
        ext = 'jpg' if mime in ('jpg', 'jpeg') else mime
        return cover.data, ext

    def get_cover_image(self) -> PILImage:
        return bytes_to_image(self.get_cover_data()[0])

    def del_cover_tag(self, save: bool = False, dry_run: bool = False):
        log.info(f'{LoggingPrefix(dry_run).remove} tags from {self}: cover')
        if not dry_run:
            self._del_cover_tag()
            if save:
                self.save()

    def _del_cover_tag(self):
        self.delete_tag(self.normalize_tag_id('cover'))

    def _log_cover_changes(self, current: list[ImageTag], cover: ImageTag, dry_run: bool):
        lp = LoggingPrefix(dry_run)
        if current:
            log.info(f'{lp.remove} existing image(s) from {self}: {current}')

        size = len(cover) if self.tag_type == 'mp4' else len(cover.data)
        log.info(f'{lp.add} cover image to {self}: [{readable_bytes(size)}] {cover!r}')
        return not dry_run

    def set_cover_data(self, image: PILImage, dry_run: bool = False, max_width: int = 1200):
        image, data, mime_type = prepare_cover_image(image, self.tag_type, max_width)
        self.set_prepared_cover_data(image, data, mime_type, dry_run)

    def set_prepared_cover_data(self, image: PILImage, data: bytes, mime_type: str, dry_run: bool = False):
        self._set_cover_data(image, data, mime_type, dry_run)
        if not dry_run:
            self.save()

    def _set_cover_data(self, image: PILImage, data: bytes, mime_type: str, dry_run: bool = False):
        raise TypeError(f'Setting cover data is not supported for {self} with type={self.tag_type!r}')

    # endregion


# region SongFile Subclasses


class Id3SongFile(SongFile):
    tag_type = 'id3'
    _f: Union[MP3, ID3FileType, WAVE]

    # region Basic Functionality

    def tags_for_id(self, tag_id: str) -> list[ID3Tag]:
        """
        :param tag_id: A tag ID
        :return: All tags from this file with the given ID
        """
        try:
            return self._f.tags.getall(tag_id.upper())  # all MP3 tags are uppercase; some MP4 tags are mixed case
        except AttributeError:
            if self._f.tags is None:
                return []
            raise

    def _normalize_tag_values(self, values):
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
        return vals

    def _get_or_create_id3_tags(self) -> ID3:
        if (tags := self._f.tags) is None:
            self._f.add_tags()
            tags = self._f.tags
        return tags

    def _normalize_tag_id_cls(self, tag_id: str) -> tuple[str, OptStr, Type[Frame]]:
        tag_id = tag_id.upper()
        try:
            tag_id, desc = tag_id.split(':', 1)
        except ValueError:
            desc = None
        try:
            tag_cls = getattr(_frames, tag_id)
        except AttributeError as e:
            raise ValueError(f'Invalid {tag_id=} for {self} - no frame class found for it') from e
        if desc and ('desc' not in (spec_fields := {spec.name: spec for spec in tag_cls._framespec})):
            raise TypeError(f'Unhandled tag type - {tag_id=} has {desc=} but {tag_cls=} has {spec_fields=}')
        return tag_id, desc, tag_cls

    def _set_text_tag(self, tag: str, tag_id: str, value, replace: bool = True):
        """
        :param tag: A tag name or ID
        :param tag_id: The normalized ID for ``tag``
        :param value: The value to store
        :param replace: Whether the value should replace any existing value(s) or be appended to them
        """
        tag_id, desc, tag_cls = self._normalize_tag_id_cls(tag_id)
        if tag_id == 'WXXX' and value and isinstance(value, str):
            a, b = value.rsplit('/', 1)
            value = f'{a}/{quote(b)}'
        if not (isinstance(value, Collection) and not isinstance(value, str)):
            value = [value]

        value_spec: Spec = tag_cls._framespec[-1]  # main value field is usually last
        value_key = value_spec.name

        kwargs = {'encoding': Encoding.UTF8} if any(s.name == 'encoding' for s in tag_cls._framespec) else {}  # noqa
        tags = self._get_or_create_id3_tags()
        if desc:  # Values with a matching desc may be replaced, others should always be retained
            values = [v for v in tags.getall(tag_id) if v.desc != desc] if replace else tags.getall(tag_id)
            values.extend(tag_cls(desc=desc, **kwargs, **{value_key: val}) for val in value)
        elif not replace and (value_key != 'text' or not isinstance(value_spec, MultiSpec)):
            spec_fields = {spec.name: spec for spec in tag_cls._framespec}
            raise TypeError(f'Unable to add {value=} for {tag=} - {tag_cls=} has {value_key=} ({spec_fields=})')
        else:
            if not replace:
                kwargs['text'] = sorted({v for t in tags.getall(tag_id) for v in t.text} | set(map(str, value)))
            elif not isinstance(value_spec.default, list) and isinstance(value, list) and len(value) == 1:
                kwargs[value_key] = value[0]
            else:
                kwargs[value_key] = sorted(map(str, value))

            log.debug(f'Creating tag with {tag_cls=} {kwargs=}')
            values = [tag_cls(**kwargs)]

        log.debug(f'Setting {self}.tags.setall({tag_id=}, {value=})')
        tags.setall(tag_id, values)

    def _delete_tag(self, tag_id: str):
        self.tags.delall(tag_id)

    # endregion

    # region Tag Cleanup

    @cached_classproperty
    def _rm_tag_matcher(cls) -> ReMatcher:  # noqa
        return ReMatcher(('TXXX(?::|$)(?!KPOP:GEN)', 'PRIV.*', 'WXXX(?::|$)(?!WIKI:A)', 'COMM.*', 'TCOP'))

    def fix_song_tags(self, dry_run: Bool = False):
        super().fix_song_tags(dry_run)
        if not isinstance((track_tags := self.tags), ID3):
            log.debug(f'Skipping tag fix due to no tags present in {self}')
            return

        tdrc = track_tags.getall('TDRC')
        txxx_date = track_tags.getall('TXXX:DATE')
        if (not tdrc) and txxx_date:
            file_date = txxx_date[0].text[0]
            rmv_msg = 'remove' if dry_run else 'removing'
            log.info(f'{LoggingPrefix(dry_run).add} TDRC={file_date} to {self} and {rmv_msg} its TXXX:DATE tag')
            if not dry_run:
                track_tags.add(TDRC(text=file_date))
                track_tags.delall('TXXX:DATE')
                self.save()

    # endregion

    # region Cover Image Methods

    def _set_cover_data(self, image: PILImage, data: bytes, mime_type: str, dry_run: bool = False):
        current = self.tags_for_id('APIC')
        cover = APIC(mime=mime_type, type=PictureType.COVER_FRONT, data=data)  # noqa
        if self._log_cover_changes(current, cover, dry_run):
            self._f.tags.delall('APIC')
            self._f.tags[cover.HashKey] = cover

    # endregion

    # region Tag Iteration Helpers

    def iter_clean_tags(self) -> Iterator[tuple[str, str, Any]]:
        for full_tag, value in self._iter_tags():
            tag = full_tag[:4]
            yield tag, self.normalize_tag_name(tag), value

    def iter_tag_id_name_values(self) -> Iterator[tuple[str, str, str, str, Any]]:
        for tag_id, tag_id, tag_name, disp_name, values in super().iter_tag_id_name_values():
            yield tag_id[:4], tag_id, tag_name, disp_name, values

    # endregion


# region MP3 & WAV


class Mp3File(Id3SongFile, ft_classes=(MP3, ID3FileType)):
    file_type = 'mp3'

    @cached_property
    def tag_version(self) -> str:
        return 'ID3v{}.{}'.format(*self._f.tags.version[:2])


class WavFile(Id3SongFile, ft_classes=(WAVE,)):
    file_type = 'wav'

    @cached_property
    def tag_version(self) -> str:
        if isinstance(self._f.tags, _WaveID3):
            return 'WAV/ID3'
        else:
            return super().tag_version

    @property
    def lossless(self) -> bool:
        return True


# endregion


class Mp4File(SongFile, ft_classes=(MP4,)):
    tag_type = 'mp4'
    file_type = 'mp4'

    # region Basic Properties & Functionality

    @cached_property
    def tag_version(self) -> str:
        return 'MP4'

    @cached_property
    def lossless(self) -> bool:
        return self._f.info.codec == 'alac'

    def _normalize_tag_values(self, values):
        vals = []
        for value in values:
            if isinstance(value, MP4FreeForm):
                if encoding := MP4_STR_ENCODINGS.get(value.dataformat):
                    vals.append(value.decode(encoding))
                else:
                    raise ValueError(f'Unexpected MP4FreeForm {value=} in {self}')
            else:
                vals.append(value)
        return vals

    def _delete_tag(self, tag_id: str):
        del self.tags[tag_id]

    # endregion

    # region Tag Cleanup

    @cached_classproperty
    def _rm_tag_matcher(cls) -> FnMatcher:  # noqa
        return FnMatcher(('*itunes*', '??ID', '?cmt', 'ownr', 'xid ', 'purd', 'desc', 'ldes', 'cprt'))

    # endregion

    # region Cover Image Methods

    def get_cover_data(self) -> tuple[bytes, str]:
        """Returns a tuple containing the raw cover data bytes, and the image type as a file extension"""
        if (cover := self.get_cover_tag()) is None:
            raise TagNotFound(f'{self} has no album cover')
        ext = 'jpg' if cover.imageformat == MP4Cover.FORMAT_JPEG else 'png'
        return cover, ext

    def _set_cover_data(self, image: PILImage, data: bytes, mime_type: str, dry_run: bool = False):
        current = self._f.tags['covr']
        try:
            cover_fmt = MP4_MIME_FORMAT_MAP[mime_type]
        except KeyError as e:
            raise ValueError(f'Invalid {mime_type=} for {self!r} - must be JPEG or PNG for MP4 cover images') from e
        cover = MP4Cover(data, cover_fmt)
        if self._log_cover_changes(current, cover, dry_run):
            self._f.tags['covr'] = [cover]

    # endregion


class VorbisSongFile(SongFile):
    tag_type = 'vorbis'
    _f: Union[FLAC, OggFLAC, OggVorbis, OggOpus]

    # region Basic Functionality

    def save(self):
        self._f.save(self._f.filename)

    def _delete_tag(self, tag_id: str):
        del self.tags[tag_id]

    # endregion

    # region Tag Cleanup

    @cached_classproperty
    def _rm_tag_matcher(cls) -> ReMatcher:  # noqa
        return ReMatcher(('UPLOAD.*', 'WWW.*', 'COMM.*', 'UPC', '(?:TRACK|DIS[CK])TOTAL'))

    def get_bad_tags(self, extras: Collection[str] = None) -> set[str] | None:
        if (track_tags := self.tags) is None:
            return None
        rm_tag_match = self._get_rm_tag_matcher(extras)
        return {tag for tag, val in track_tags if rm_tag_match(tag)}

    # endregion

    # region Cover Image Methods

    def get_cover_tag(self) -> Picture | None:
        try:
            return self._f.pictures[0]  # FLAC
        except IndexError:
            return None
        except AttributeError:
            pass
        # Note: This uses `metadata_block_picture`, but apparently some programs may use `coverart` + `coverartmime`
        # instead: https://mutagen.readthedocs.io/en/latest/user/vcomment.html
        cover = self.get_tag('cover')
        if isinstance(cover, Picture):  # FLAC
            return cover
        return Picture(b64decode(cover))

    def _set_cover_data(self, image: PILImage, data: bytes, mime_type: str, dry_run: bool = False):
        try:
            current = self._f.pictures
        except AttributeError:
            current = self.get_cover_tag()

        cover = Picture()
        cover.type = PictureType.COVER_FRONT  # noqa
        cover.mime = mime_type
        cover.width, cover.height = image.size
        cover.depth = 1 if image.mode == '1' else 32 if image.mode in ('I', 'F') else 8 * len(image.getbands())
        cover.data = data
        if self._log_cover_changes(current, cover, dry_run):
            try:
                self._f.clear_pictures()
            except AttributeError:  # Ogg
                self._f['metadata_block_picture'] = [b64encode(cover.write()).decode('ascii')]
            else:
                self._f.add_picture(cover)

    def _del_cover_tag(self):
        self._f.clear_pictures()

    # endregion


# region Flac & Ogg


class FlacFile(VorbisSongFile, ft_classes=(FLAC,)):
    file_type = 'flac'

    @cached_property
    def tag_version(self) -> str:
        return 'FLAC'

    @property
    def lossless(self) -> bool:
        return True


class OggFile(VorbisSongFile, ft_classes=(OggFileType, OggFLAC, OggVorbis, OggOpus)):
    file_type = 'ogg'

    @cached_property
    def tag_version(self) -> str:
        file = self._f
        if isinstance(file, OggFLAC):
            return 'OGG[flac]'
        elif isinstance(file, OggVorbis):
            return 'OGG[vorbis]'
        elif isinstance(file, OggOpus):
            return 'OGG[opus]'
        return 'OGG[unknown]'

    @cached_property
    def lossless(self) -> bool:
        return isinstance(self._f, OggFLAC)


# endregion

# endregion


def iter_music_files(paths: Paths) -> Iterator[SongFile]:
    non_music_exts = {'.jpg', '.jpeg', '.png', '.jfif', '.part', '.pdf', '.zip', '.webp'}
    for file_path in iter_files(paths):
        if music_file := SongFile(file_path):
            yield music_file
        else:
            if file_path.suffix not in non_music_exts:
                log.log(5, f'Not a music file: {file_path}')


if __name__ == '__main__':
    from ..patches import apply_mutagen_patches

    apply_mutagen_patches()
