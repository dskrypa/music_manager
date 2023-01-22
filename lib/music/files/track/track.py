"""
Song File / Audio Track

:author: Doug Skrypa
"""

from __future__ import annotations

import logging
import os
import struct
from base64 import b64decode, b64encode
from datetime import date
from hashlib import sha256
from io import BytesIO
from itertools import chain
from pathlib import Path
from platform import system
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Optional, Union, Iterator, Any, Iterable, Collection, Pattern, Type
from urllib.parse import quote

from mutagen import File, FileType
from mutagen.flac import VCFLACDict, FLAC, Picture
from mutagen.id3 import ID3, POPM, Frames, _frames, ID3FileType, APIC, PictureType, Encoding
from mutagen.id3._specs import MultiSpec, Spec
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4Tags, MP4, MP4Cover, AtomDataType, MP4FreeForm
from mutagen.ogg import OggFileType, OggPage
from mutagen.oggflac import OggFLAC
from mutagen.oggvorbis import OggVorbis
from mutagen.oggopus import OggOpus
from mutagen.wave import WAVE, _WaveID3
from plexapi.audio import Track

from ds_tools.caching.decorators import cached_property
from ds_tools.caching.mixins import ClearableCachedPropertyMixin
from ds_tools.fs.paths import iter_files, Paths
from ds_tools.output.formatting import readable_bytes

from music.common.ratings import stars_to_256, stars_from_256, stars
from music.common.utils import format_duration
from music.constants import TYPED_TAG_MAP, TYPED_TAG_DISPLAY_NAME_MAP, TAG_NAME_DISPLAY_NAME_MAP
from music.text.name import Name
from ..cover import prepare_cover_image
from ..exceptions import InvalidTagName, TagException, TagNotFound, TagValueException, UnsupportedTagForFileType
from ..parsing import split_artists, AlbumName
from ..paths import FileBasedObject, PathLike
from .descriptors import MusicFileProperty, TextTagProperty, TagValuesProperty, _NotSet
from .patterns import (
    EXTRACT_PART_MATCH, LYRIC_URL_MATCH, SAMPLE_RATE_PAT, compiled_fnmatch_patterns, cleanup_album_name
)
from .utils import tag_repr, parse_file_date, tag_id_to_name_map_for_type

if TYPE_CHECKING:
    from numpy import ndarray
    from PIL import Image
    from pydub import AudioSegment
    from music.typing import OptStr

__all__ = ['SongFile', 'iter_music_files']
log = logging.getLogger(__name__)

ON_WINDOWS = system().lower() == 'windows'
MP4_STR_ENCODINGS = {AtomDataType.UTF8: 'utf-8', AtomDataType.UTF16: 'utf-16be'}  # noqa
MP4_MIME_FORMAT_MAP = {'image/jpeg': MP4Cover.FORMAT_JPEG, 'image/png': MP4Cover.FORMAT_PNG}

MutagenFile = Union[MP3, MP4, FLAC, FileType]
ImageTag = Union[APIC, MP4Cover, Picture]


class SongFile(ClearableCachedPropertyMixin, FileBasedObject):
    """Adds some properties/methods to mutagen.File types that facilitate other functions"""
    tag_type: OptStr = None
    file_type: OptStr = None
    __ft_cls_map = {}
    __instances = {}                                                    # type: dict[Path, SongFile]
    _bpm = None                                                         # type: Optional[int]
    _f = None                                                           # type: Optional[MutagenFile]
    _path = None                                                        # type: Optional[Path]
    tags = MusicFileProperty('tags')                                    # type: Union[ID3, MP4Tags, VCFLACDict]
    filename = MusicFileProperty('filename')                            # type: str
    length = MusicFileProperty('info.length')                           # type: float   # length of this song in seconds
    channels = MusicFileProperty('info.channels')                       # type: int
    bits_per_sample = MusicFileProperty('info.bits_per_sample')         # type: int
    _bitrate = MusicFileProperty('info.bitrate')                        # type: int
    _sample_rate = MusicFileProperty('info.sample_rate')                # type: int
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

    def __init_subclass__(cls, ft_classes: Collection[Type[FileType]] = (), **kwargs):
        super().__init_subclass__(**kwargs)
        for c in ft_classes:
            cls.__ft_cls_map[c] = cls

    def __new__(cls, file_path: PathLike, *args, options=_NotSet, **kwargs):
        file_path = Path(file_path).expanduser().resolve() if isinstance(file_path, str) else file_path
        try:
            return cls.__instances[file_path]
        except KeyError:
            if (music_file := cls._new_file(file_path, *args, options=options, **kwargs)) is not None:
                mf_cls = cls.__ft_cls_map.get(type(music_file), cls)
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

    # region Internal Methods

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

    # endregion

    @cached_property
    def extended_repr(self) -> str:
        try:
            info = f'[{self.tag_title!r} by {self.tag_artist}, in {self.album_name_cleaned!r}]'
        except Exception:  # noqa
            info = ''
        return f'<{self.__class__.__name__}({self.rel_path!r}){info}>'

    @property
    def path(self) -> Path:
        return self._path

    def rename(self, dest_path: PathLike):
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
                raise ValueError(f'Destination for {self} already exists: {dest_path.as_posix()!r}')

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
        self._f.tags.save(self._f.filename)

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

    # region Add/Remove/Get Tags

    def delete_tag(self, tag_id: str, save: bool = False):
        # TODO: When multiple values exist for the tag, make it possible to delete a specific index/value?
        self._delete_tag(tag_id)
        if save:
            self.save()

    def _delete_tag(self, tag_id: str):
        raise TypeError(f'Cannot delete tag_id={tag_id!r} for {self} because its tag type={self.tag_type!r}')

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

        normalized = filter(None, self._normalize_tag_values(values))
        if strip:
            return [value.strip() if isinstance(value, str) else value for value in normalized]
        else:
            return list(normalized)

    def _normalize_tag_values(self, values):
        return values

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
        id3 = self.tag_type == 'id3'
        for tag, value in self._f.tags.items():
            _tag = tag[:4] if id3 else tag
            yield _tag, self.normalize_tag_name(_tag), value

    def iter_tag_id_name_values(self) -> Iterator[tuple[str, str, str, str, Any]]:
        id3 = self.tag_type == 'id3'
        for tag_id, value in self._f.tags.items():
            disp_name = self._get_tag_display_name(tag_id)
            trunc_id = tag_id[:4] if id3 else tag_id
            tag_name = self.normalize_tag_name(tag_id)
            # log.debug(f'Processing values for {tag_name=} {tag_id=} {value=} on {self}')
            if values := self._normalize_values(value):
                if isinstance(values, list) and len(values) == 1 and disp_name != 'Genre':
                    values = values[0]
                yield trunc_id, tag_id, tag_name, disp_name, values

    # endregion

    # region Tag-Related Properties

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
    def title_as_album_name(self) -> Optional[AlbumName]:
        # Intended for use for singles with no album name tag
        if title := self.tag_title:
            return AlbumName.parse(title, self.tag_artist)
        return None

    @cached_property
    def year(self) -> Optional[int]:
        try:
            return self.date.year
        except Exception:  # noqa
            return None

    def _num_tag(self, name: str) -> int:
        orig = value = self.tag_text(name, default=None)
        if value:
            if '/' in value:
                value = value.split('/', 1)[0].strip()
            if ',' in value:
                value = value.split(',', 1)[0].strip()
            if value.startswith('('):
                value = value[1:].strip()

            try:
                value = int(value)
            except Exception as e:
                log.debug(f'{self}: Error converting {name} num={orig!r} [{value!r}] to int: {e}')
                value = 0
        return value or 0

    @cached_property
    def track_num(self) -> int:
        return self._num_tag('track')

    @cached_property
    def disk_num(self) -> int:
        return self._num_tag('disk')

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

    @cached_property
    def album_name_cleaned(self) -> str:
        return cleanup_album_name(self.tag_album, self.tag_artist) or self.tag_album

    @cached_property
    def album_name_cleaned_plus_and_part(self) -> tuple[str, Optional[str]]:
        """Tuple of title, part"""
        return _extract_album_part(self.album_name_cleaned)

    # endregion

    # region Hash / Fingerprint Methods

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

    # endregion

    # region Tag Cleanup

    def _log_update(self, tag_name: str, orig_val: str, new_val: str, dry_run: bool):
        prefix, upd_msg = ('[DRY RUN] ', 'Would update') if dry_run else ('', 'Updating')
        log.info(f'{prefix}{upd_msg} {tag_name} for {self} from {tag_repr(orig_val)!r} to {tag_repr(new_val)!r}')

    def cleanup_title(self, dry_run: bool = False, only_matching: bool = False):
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

    def cleanup_lyrics(self, dry_run: bool = False):
        changes = 0
        tag_type = self.tag_type
        new_lyrics = []
        for lyric_tag in self.tags_for_name('lyrics'):
            lyric = lyric_tag.text if tag_type == 'id3' else lyric_tag
            if m := LYRIC_URL_MATCH(lyric):
                new_lyric = m.group(1).strip() + '\r\n'
                self._log_update('lyrics', lyric, new_lyric, dry_run)
                if not dry_run:
                    if tag_type == 'id3':
                        lyric_tag.text = new_lyric
                    else:
                        new_lyrics.append(new_lyric)
                    changes += 1
            else:
                new_lyrics.append(lyric)

        if changes and not dry_run:
            log.info(f'Saving changes to lyrics in {self}')
            if tag_type != 'id3':
                self.set_text_tag('lyrics', new_lyrics)
            self.save()

    # endregion

    # region BPM

    def bpm(self, save: bool = True, calculate: bool = True) -> Optional[int]:
        """
        :param save: If the BPM was not already stored in a tag, save the calculated BPM in a tag.
        :param calculate: If the BPM was not already stored in a tag, calculate it
        :return int: This track's BPM from a tag if available, or calculated
        """
        try:
            bpm = int(self.tag_text('bpm'))
        except (TagException, ValueError):
            if calculate:
                bpm = self._calculate_bpm(save)
            else:
                bpm = None

        if bpm == 0 and calculate:
            bpm = self._calculate_bpm(save)

        return bpm

    def _calculate_bpm(self, save: bool = True):
        from .bpm import get_bpm

        if not (bpm := self._bpm):
            bpm = self._bpm = get_bpm(self.path, self.sample_rate)
        if save:
            self.set_text_tag('bpm', bpm)
            log.debug(f'Saving {bpm=} for {self}')
            self.save()

        return bpm

    # endregion

    # region Tag Updates

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

    def get_tag_updates(
        self,
        tag_ids: Iterable[str],
        value: str,
        patterns: Iterable[Union[str, Pattern]] = None,
        partial: bool = False,
    ):
        if partial and not patterns:
            raise ValueError('Unable to perform partial tag update without any patterns')
        patterns = compiled_fnmatch_patterns(patterns)
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
        return self.get_tag('cover')

    def get_cover_data(self) -> tuple[bytes, str]:
        """Returns a tuple containing the raw cover data bytes, and the image type as a file extension"""
        if self.tag_type in ('id3', 'vorbis'):
            if (cover := self.get_cover_tag()) is None:
                raise TagNotFound(f'{self} has no album cover')
            mime = cover.mime.split('/')[-1].lower()
            ext = 'jpg' if mime in ('jpg', 'jpeg') else mime
            return cover.data, ext
        else:
            raise TypeError(f'{self} has unexpected type={self.tag_type!r} for album cover extraction')

    def get_cover_image(self, extras: bool = False) -> Union[Image.Image, tuple[Image.Image, bytes, str]]:
        from PIL import Image

        data, ext = self.get_cover_data()
        image = Image.open(BytesIO(data))
        return (image, data, ext) if extras else image

    def del_cover_tag(self, save: bool = False, dry_run: bool = False):
        prefix = '[DRY RUN] Would remove' if dry_run else 'Removing'
        log.info(f'{prefix} tags from {self}: cover')
        if not dry_run:
            if self.tag_type == 'vorbis':
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

    def set_cover_data(self, image: Image.Image, dry_run: bool = False, max_width: int = 1200):
        image, data, mime_type = prepare_cover_image(image, self.tag_type, max_width)
        self._set_cover_data(image, data, mime_type, dry_run)
        if not dry_run:
            self.save()

    def _set_cover_data(self, image: Image.Image, data: bytes, mime_type: str, dry_run: bool = False):
        pass

    # endregion

    # region Experimental

    @cached_property
    def decibels(self) -> ndarray:
        from librosa import load, stft, amplitude_to_db

        data, sample_rate = load(self.path, sr=None, mono=False)
        stft_coefficients = stft(data)  # short-term Fourier transform coefficients
        return amplitude_to_db(abs(stft_coefficients))

    @cached_property
    def audio_segment(self) -> AudioSegment:
        from pydub import AudioSegment

        return AudioSegment.from_file(self.path)

    # endregion


class Id3SongFile(SongFile):
    tag_type = 'id3'
    _f: Union[MP3, ID3FileType, WAVE]

    def tags_for_id(self, tag_id: str):
        """
        :param str tag_id: A tag ID
        :return list: All tags from this file with the given ID
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

    def _set_text_tag(self, tag: str, tag_id: str, value, replace: bool = True):
        tags = self._f.tags  # type: ID3
        if tags is None:
            self._f.add_tags()
            tags = self._f.tags
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
        if tag_id == 'WXXX' and value and isinstance(value, str):
            a, b = value.rsplit('/', 1)
            value = f'{a}/{quote(b)}'
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

    def _delete_tag(self, tag_id: str):
        self.tags.delall(tag_id)

    def _set_cover_data(self, image: Image.Image, data: bytes, mime_type: str, dry_run: bool = False):
        current = self.tags_for_id('APIC')
        cover = APIC(mime=mime_type, type=PictureType.COVER_FRONT, data=data)  # noqa
        if self._log_cover_changes(current, cover, dry_run):
            self._f.tags.delall('APIC')
            self._f.tags[cover.HashKey] = cover


class Mp3SongFile(Id3SongFile, ft_classes=(MP3, ID3FileType)):
    file_type = 'mp3'

    @cached_property
    def tag_version(self) -> str:
        return 'ID3v{}.{}'.format(*self._f.tags.version[:2])


class WavSongFile(Id3SongFile, ft_classes=(WAVE,)):
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


class Mp4SongFile(SongFile, ft_classes=(MP4,)):
    tag_type = 'mp4'
    file_type = 'mp4'

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

    def get_cover_data(self) -> tuple[bytes, str]:
        """Returns a tuple containing the raw cover data bytes, and the image type as a file extension"""
        if (cover := self.get_cover_tag()) is None:
            raise TagNotFound(f'{self} has no album cover')
        ext = 'jpg' if cover.imageformat == MP4Cover.FORMAT_JPEG else 'png'
        return cover, ext

    def _set_cover_data(self, image: Image.Image, data: bytes, mime_type: str, dry_run: bool = False):
        current = self._f.tags['covr']
        try:
            cover_fmt = MP4_MIME_FORMAT_MAP[mime_type]
        except KeyError as e:
            raise ValueError(f'Invalid {mime_type=} for {self!r} - must be JPEG or PNG for MP4 cover images') from e
        cover = MP4Cover(data, cover_fmt)
        if self._log_cover_changes(current, cover, dry_run):
            self._f.tags['covr'] = [cover]


class VorbisSongFile(SongFile):
    tag_type = 'vorbis'
    _f: Union[FLAC, OggFLAC, OggVorbis, OggOpus]

    def save(self):
        self._f.save(self._f.filename)

    def _delete_tag(self, tag_id: str):
        del self.tags[tag_id]

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

    def _set_cover_data(self, image: Image.Image, data: bytes, mime_type: str, dry_run: bool = False):
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


class FlacSongFile(VorbisSongFile, ft_classes=(FLAC,)):
    file_type = 'flac'

    @cached_property
    def tag_version(self) -> str:
        return 'FLAC'

    @property
    def lossless(self) -> bool:
        return True


class OggSongFile(VorbisSongFile, ft_classes=(OggFileType, OggFLAC, OggVorbis, OggOpus)):
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


def iter_music_files(paths: Paths) -> Iterator[SongFile]:
    non_music_exts = {'.jpg', '.jpeg', '.png', '.jfif', '.part', '.pdf', '.zip', '.webp'}
    for file_path in iter_files(paths):
        music_file = SongFile(file_path)
        if music_file:
            yield music_file
        else:
            if file_path.suffix not in non_music_exts:
                log.log(5, f'Not a music file: {file_path}')


def _extract_album_part(title: str) -> tuple[str, Optional[str]]:
    part = None
    if m := EXTRACT_PART_MATCH(title):
        title, part = map(str.strip, m.groups())
    if title.endswith(' -'):
        title = title[:-1].strip()
    return title, part


if __name__ == '__main__':
    from ..patches import apply_mutagen_patches

    apply_mutagen_patches()
