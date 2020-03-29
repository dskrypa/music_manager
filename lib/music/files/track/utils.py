"""
:author: Doug Skrypa
"""

import re
import string
from pathlib import Path
from typing import Mapping, Tuple, Any, Callable, Optional
from unicodedata import normalize

from ds_tools.caching import ClearableCachedProperty
from ds_tools.compat import cached_property
from ds_tools.output import colored, uprint
from ds_tools.output.table import mono_width

__all__ = [
    'MusicFileProperty', 'RATING_RANGES', 'TYPED_TAG_MAP', 'FileBasedObject', 'TextTagProperty', 'print_tag_changes',
    'tag_repr'
]

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
    'isrc': {'mp4': '----:com.apple.iTunes:ISRC', 'mp3': 'TSRC'},   # International Standard Recording Code
    'compilation': {'mp4': 'cpil', 'mp3': 'TCMP'},
    'podcast': {'mp4': 'pcst', 'mp3': 'PCST'},
    'bpm': {'mp4': 'tmpo', 'mp3': 'TBPM'},
    'language': {'mp4': '----:com.apple.iTunes:LANGUAGE', 'mp3': 'TLAN'},
    'lyrics': {'mp4': '\xa9lyr', 'mp3': 'USLT'},
    # 'name': {'mp4': '', 'mp3': ''},
}
# Translate whitespace characters (such as \n, \r, etc.) to their escape sequences
WHITESPACE_TRANS_TBL = str.maketrans({c: c.encode('unicode_escape').decode('utf-8') for c in string.whitespace})


def tag_repr(tag_val, max_len=125, sub_len=25):
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

    def __init__(self, name: str, cast_func: Optional[Callable] = None):
        self.tag_name = name
        self.cast_func = cast_func

    def __get__(self, instance, cls):
        if instance is None:
            return self
        value = instance.tag_text(self.tag_name)
        if self.cast_func is not None:
            value = self.cast_func(value)
        instance.__dict__[self.name] = value
        return value

    def __set__(self, instance, value):
        instance.set_text_tag(self.tag_name, value, by_id=False)

    def __delete__(self, instance):
        instance.delete_tag(instance.tag_name_to_id(self.tag_name))


def print_tag_changes(obj, changes: Mapping[str, Tuple[Any, Any]], dry_run, color=None):
    name_width = max(len(tag_name) for tag_name in changes)
    orig_width = max(max(len(r), mono_width(r)) for r in (repr(orig) for orig, _ in changes.values()))
    _fmt = '  - {{:<{}s}}{}{{:>{}s}}{}{{}}'
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
