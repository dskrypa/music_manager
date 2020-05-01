"""
:author: Doug Skrypa
"""

import logging
import platform
import re
import string
from datetime import datetime, date
from pathlib import Path
from typing import TYPE_CHECKING, Mapping, Tuple, Any, Callable, Optional, Type
from unicodedata import normalize

from mutagen.id3 import POPM, USLT, APIC

from ds_tools.caching import ClearableCachedProperty
from ds_tools.compat import cached_property
from ds_tools.output import colored, uprint
from ds_tools.output.table import mono_width
from ...common import stars

if TYPE_CHECKING:
    from .base import BaseSongFile

__all__ = [
    'MusicFileProperty', 'RATING_RANGES', 'TYPED_TAG_MAP', 'FileBasedObject', 'TextTagProperty', 'print_tag_changes',
    'tag_repr', 'ON_WINDOWS', 'stars_from_256', 'parse_file_date'
]
log = logging.getLogger(__name__)

ON_WINDOWS = platform.system().lower() == 'windows'
RATING_RANGES = [(1, 31, 15), (32, 95, 64), (96, 159, 128), (160, 223, 196), (224, 255, 255)]
TYPED_TAG_MAP = {   # See: https://wiki.hydrogenaud.io/index.php?title=Tag_Mapping
    'title': {'mp4': '\xa9nam', 'mp3': 'TIT2', 'flac': 'TITLE'},
    'date': {'mp4': '\xa9day', 'mp3': 'TDRC', 'flac': 'DATE'},
    'genre': {'mp4': '\xa9gen', 'mp3': 'TCON', 'flac': 'GENRE'},
    'album': {'mp4': '\xa9alb', 'mp3': 'TALB', 'flac': 'ALBUM'},
    'artist': {'mp4': '\xa9ART', 'mp3': 'TPE1', 'flac': 'ARTIST'},
    'album_artist': {'mp4': 'aART', 'mp3': 'TPE2', 'flac': 'ALBUMARTIST'},
    'track': {'mp4': 'trkn', 'mp3': 'TRCK', 'flac': 'TRACKNUMBER'},
    'disk': {'mp4': 'disk', 'mp3': 'TPOS', 'flac': 'DISCNUMBER'},
    'grouping': {'mp4': '\xa9grp', 'mp3': 'TIT1', 'flac': 'GROUPING'},
    'album_sort_order': {'mp4': 'soal', 'mp3': 'TSOA', 'flac': 'ALBUMSORT'},
    'track_sort_order': {'mp4': 'sonm', 'mp3': 'TSOT', 'flac': 'TITLESORT'},
    'album_artist_sort_order': {'mp4': 'soaa', 'mp3': 'TSO2', 'flac': 'ALBUMARTISTSORT'},
    'track_artist_sort_order': {'mp4': 'soar', 'mp3': 'TSOP', 'flac': 'ARTISTSORT'},
    'isrc': {'mp4': '----:com.apple.iTunes:ISRC', 'mp3': 'TSRC', 'flac': 'ISRC'},  # International Standard Recording Code
    'compilation': {'mp4': 'cpil', 'mp3': 'TCMP', 'flac': 'COMPILATION'},
    'podcast': {'mp4': 'pcst', 'mp3': 'PCST'},  # flac: None
    'bpm': {'mp4': 'tmpo', 'mp3': 'TBPM', 'flac': 'BPM'},
    'language': {'mp4': '----:com.apple.iTunes:LANGUAGE', 'mp3': 'TLAN', 'flac': 'LANGUAGE'},
    'lyrics': {'mp4': '\xa9lyr', 'mp3': 'USLT', 'flac': 'LYRICS'},
    # 'name': {'mp4': '', 'mp3': '', 'flac': ''},
}
# Translate whitespace characters (such as \n, \r, etc.) to their escape sequences
WHITESPACE_TRANS_TBL = str.maketrans({c: c.encode('unicode_escape').decode('utf-8') for c in string.whitespace})
_NotSet = object()


def tag_repr(tag_val, max_len=None, sub_len=None):
    if isinstance(tag_val, POPM):
        # noinspection PyUnresolvedReferences
        return stars(stars_from_256(tag_val.rating, 10))
    elif isinstance(tag_val, APIC) and max_len is None and sub_len is None:
        return '<APIC>'
    elif isinstance(tag_val, USLT) and max_len is None and sub_len is None:
        max_len, sub_len = 45, 20
    else:
        max_len = max_len or 125
        sub_len = sub_len or 25

    tag_val = normalize('NFC', str(tag_val)).translate(WHITESPACE_TRANS_TBL)
    if len(tag_val) > max_len:
        return '{}...{}'.format(tag_val[:sub_len], tag_val[-sub_len:])
    return tag_val


class FileBasedObject:
    __fspath__ = None

    @cached_property
    def path(self) -> Path:
        return Path(self.__fspath__).resolve()

    @property
    def rel_path(self) -> str:
        try:
            return self.path.relative_to(Path('.').resolve()).as_posix()
        except Exception:
            return self.path.as_posix()

    def basename(self, no_ext=False, trim_prefix=False) -> str:
        basename = self.path.stem if no_ext else self.path.name
        if trim_prefix:
            m = re.match(r'\d+\.?\s*(.*)', basename)
            if m:
                basename = m.group(1)
        return basename

    @cached_property
    def ext(self) -> str:
        return self.path.suffix[1:]


class MusicFileProperty(ClearableCachedProperty):
    _set_name = True

    def __init__(self, name):
        self.parts = name.split('.')

    def __get__(self, obj, owner):
        if obj is None:
            return self
        value = obj._f
        for part in self.parts:
            value = getattr(value, part)
        obj.__dict__[self.name] = value
        return value


class TextTagProperty(ClearableCachedProperty):
    _set_name = True

    def __init__(self, name: str, cast_func: Optional[Callable] = None, default: Any = _NotSet):
        self.tag_name = name
        self.cast_func = cast_func
        self.default = default

    def __get__(self, instance: 'BaseSongFile', cls: Type['BaseSongFile']):
        if instance is None:
            return self
        value = instance.tag_text(self.tag_name, default=self.default)
        value = value.replace('\xa0', ' ')
        if self.cast_func is not None:
            value = self.cast_func(value)
        instance.__dict__[self.name] = value
        return value

    def __set__(self, instance, value):
        instance.set_text_tag(self.tag_name, value, by_id=False)

    def __delete__(self, instance):
        instance.delete_tag(instance.tag_name_to_id(self.tag_name))


def print_tag_changes(obj, changes: Mapping[str, Tuple[Any, Any]], dry_run, color=None):
    name_width = max(len(tag_name) for tag_name in changes) if changes else 0
    orig_width = max(max(len(r), mono_width(r)) for r in (repr(orig) for orig, _ in changes.values())) if changes else 0
    _fmt = '  - {{:<{}s}}{}{{:>{}s}}{}{{}}'

    if changes:
        uprint(colored('{} {} by changing...'.format('[DRY RUN] Would update' if dry_run else 'Updating', obj), color))
        for tag_name, (orig_val, new_val) in changes.items():
            if tag_name == 'title':
                bg, reset, w = 20, False, 20
            else:
                bg, reset, w = None, True, 14

            orig_repr = repr(orig_val)
            fmt = _fmt.format(
                name_width + w, colored(' from ', 15, bg, reset=reset),
                orig_width - (mono_width(orig_repr) - len(orig_repr)) + w, colored(' to ', 15, bg, reset=reset)
            )

            uprint(colored(
                fmt.format(
                    colored(tag_name, 14, bg, reset=reset), colored(orig_repr, 11, bg, reset=reset),
                    colored(repr(new_val), 10, bg, reset=reset)
                ), bg_color=bg
            ))
    else:
        prefix = '[DRY RUN] ' if dry_run else ''
        uprint(colored(f'{prefix}No changes necessary for {obj}', color))


def stars_from_256(rating: int, out_of=5) -> int:
    if not (0 <= rating <= 255):
        raise ValueError(f'{rating=} is outside the range of 0-255')
    elif out_of == 256:
        return rating
    elif out_of not in (5, 10):
        raise ValueError(f'{out_of=} is invalid - must be 5, 10, or 256')

    for stars_5, (a, b, c) in enumerate(RATING_RANGES, 1):
        if a <= rating <= b:
            if out_of == 5:
                return stars_5
            a, b, c = RATING_RANGES[stars_5 - 1]
            if stars_5 == 1 and rating < c:
                return 1
            stars_10 = stars_5 * 2
            return stars_10 + 1 if rating > c else stars_10


def parse_file_date(dt_str) -> Optional[date]:
    for fmt in ('%Y%m%d', '%Y-%m-%d', '%Y'):
        try:
            return datetime.strptime(dt_str, fmt).date()
        except ValueError:
            pass
    return None
