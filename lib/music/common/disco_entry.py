"""
:author: Doug Skrypa
"""

import logging
from enum import Enum
from functools import cached_property
from typing import Iterable, Optional, Union, List

from ds_tools.core.decorate import cached_classproperty

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

    def __repr__(self):
        return f'<{type(self).__name__}: {self.value[0]!r}>'

    def __bool__(self):
        return self is not DiscoEntryType.UNKNOWN

    def __lt__(self, other: 'DiscoEntryType'):
        return self._members.index(self) < self._members.index(other)

    def compatible_with(self, other: 'DiscoEntryType') -> bool:
        if self == other:
            return True

        types = {self, other}
        if DiscoEntryType.ExtendedPlay in types:
            return bool(types.intersection({DiscoEntryType.MiniAlbum, DiscoEntryType.SingleAlbum}))
        return False

    # noinspection PyMethodParameters
    @cached_classproperty
    def _members(cls) -> List['DiscoEntryType']:
        return list(cls.__members__.values())

    @classmethod
    def _for_category(cls, category: str) -> Optional['DiscoEntryType']:
        _category = category.lower().strip().replace('-', ' ').replace('_', ' ')
        for album_type in cls:
            if any(cat in _category for cat in album_type.categories):
                # log.debug(f'{category!r} => {album_type}')
                return album_type

        if _category == 'ep':
            return cls.ExtendedPlay
        return None

    @classmethod
    def for_name(cls, name: Union[str, Iterable[str], None]) -> 'DiscoEntryType':
        if name:
            candidates = set()
            if isinstance(name, str):
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

            log.debug(f'No DiscoEntryType exists for name={name!r}', stack_info=True)
        return cls.UNKNOWN

    @cached_property
    def real_name(self):
        return self.value[0]

    @cached_property
    def categories(self):
        return self.value[1]

    @cached_property
    def directory(self):
        return self.value[2]

    @cached_property
    def numbered(self):
        return self.value[3]
