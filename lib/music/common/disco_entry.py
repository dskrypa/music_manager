"""
:author: Doug Skrypa
"""

from __future__ import annotations

import logging
import re
from enum import Enum
from functools import cached_property
from typing import TYPE_CHECKING, Iterable, Optional, Union

from ds_tools.core.decorate import cached_classproperty
from ds_tools.output.formatting import ordinal_suffix

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ['DiscoEntryType']
log = logging.getLogger(__name__)


class DiscoEntryType(Enum):
    # Format: real_name, categories, directory, numbered
    UNKNOWN = 'UNKNOWN', (), 'Other', False
    MiniAlbum = 'Mini Album', ('mini album',), 'Mini Albums', True
    ExtendedPlay = 'EP', ('extended play', 'digital eps'), 'EPs', False
    SingleAlbum = 'Single Album', ('single album',), 'Single Albums', True
    SpecialAlbum = 'Special Album', ('special album',), 'Special Albums', True
    Compilation = 'Compilation', ('compilation', 'best album'), 'Compilations', False
    Feature = 'Feature', ('feature',), 'Collaborations', False
    Live = 'Live Album', ('live album',), 'Live', False
    Competition = 'Competition', ('participation release',), 'Other', False
    MixTape = 'MixTape', ('mixtape',), 'Other', False
    CoverAlbum = 'Cover Album', ('cover album', 'remake album'), 'Other', False
    Soundtrack = 'Soundtrack', ('soundtrack', 'ost'), 'Soundtracks', False
    Single = (
        'Single', (
            'single', 'song', 'digital single', 'promotional single', 'special single', 'other release',
            'digital download'
        ),
        'Singles', False
    )
    Album = 'Album', ('studio album', 'repackage album', 'full-length album', 'album'), 'Albums', True
    Collaboration = 'Collaboration', ('collaboration',), 'Collaborations', False
    Christmas = 'Christmas', ('christmas',), 'Christmas', False
    Holiday = 'Holiday', ('holiday',), 'Holiday', False
    _OTHER = '_OTHER', ('others',), 'Other', False

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__}: {self.value[0]!r}>'

    def __bool__(self) -> bool:
        return self is not DiscoEntryType.UNKNOWN

    def __lt__(self, other: DiscoEntryType):
        return self._members.index(self) < self._members.index(other)  # noqa

    def compatible_with(self, other: DiscoEntryType) -> bool:
        if self == other:
            return True

        types = {self, other}
        if DiscoEntryType.ExtendedPlay in types:
            return bool(types.intersection({DiscoEntryType.MiniAlbum, DiscoEntryType.SingleAlbum}))
        return False

    # noinspection PyMethodParameters
    @cached_classproperty
    def _members(cls) -> list[DiscoEntryType]:
        return list(cls.__members__.values())  # noqa

    @classmethod
    def _for_category(cls, category: str) -> Optional[DiscoEntryType]:
        _category = category.lower().strip().replace('-', ' ').replace('_', ' ')
        for album_type in cls:
            if any(cat in _category for cat in album_type.categories):
                # log.debug(f'{category!r} => {album_type}')
                return album_type

        if _category in {'ep', 'eps'}:
            return cls.ExtendedPlay
        return None

    @classmethod
    def for_name(cls, name: Union[str, Iterable[str], None], stack_info: bool = True) -> DiscoEntryType:
        if not name:
            return cls.UNKNOWN
        elif is_str := isinstance(name, str):
            try:
                return cls[name]
            except KeyError:
                pass

        candidates = set()
        if is_str:
            if album_type := cls._for_category(name):
                candidates.add(album_type)
        else:
            for _name in name:
                if album_type := cls._for_category(_name):
                    candidates.add(album_type)

        if candidates:
            if len(candidates) == 1:
                candidate = next(iter(candidates))
            else:
                candidate = min(candidates)
            return cls.UNKNOWN if candidate is cls._OTHER else candidate

        if name != 'UNKNOWN':
            log.debug(f'No DiscoEntryType exists for {name=}', stack_info=stack_info)
        return cls.UNKNOWN

    @classmethod
    def for_directory(cls, dir_name: str) -> DiscoEntryType | None:
        for album_type in cls:
            if album_type.directory == dir_name:
                return album_type
        return None

    @classmethod
    def _missing_(cls, value):
        return cls.for_name(value)  # noqa

    @cached_property
    def real_name(self) -> str:
        return self.value[0]

    @cached_property
    def categories(self) -> tuple[str, ...]:
        return self.value[1]

    @cached_property
    def directory(self) -> str:
        return self.value[2]

    @cached_property
    def numbered(self) -> bool:
        return self.value[3]

    def format(self, num: int) -> str:
        return f'{num}{ordinal_suffix(num)} {self.real_name}'

    @classmethod
    def with_num_from_album_dir(cls, path: Path, default_num: int = 1) -> tuple[DiscoEntryType, int] | None:
        if not (album_type := cls.for_directory(path.parent.name)):
            return None

        if m := re.search(r'\[(\d+)(?:st|nd|rd|th) ([^]]+)]$', path.name):
            num_str, type_name = m.groups()
            if type_name == album_type.real_name:
                return album_type, int(num_str)

        if not album_type.numbered:
            return album_type, default_num

        return None
