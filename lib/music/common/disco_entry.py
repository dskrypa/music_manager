"""
:author: Doug Skrypa
"""

import logging
from enum import Enum

from ds_tools.compat import cached_property

__all__ = ['DiscoEntryType']
log = logging.getLogger(__name__)


class DiscoEntryType(Enum):
    # Format: real_name, categories, directory, numbered
    UNKNOWN = 'UNKNOWN', (), 'Other', False
    MiniAlbum = 'Mini Album', ('mini album',), 'Mini Albums', True
    ExtendedPlay = 'EP', ('extended play',), 'EPs', False
    SingleAlbum = 'Single Album', ('single album',), 'Single Albums', True
    SpecialAlbum = 'Special Album', ('special album',), 'Special Albums', True
    Compilation = 'Compilation', ('compilation', 'best album'), 'Compilations', False
    Feature = 'Feature', ('feature',), 'Collaborations', False
    Collaboration = 'Collaboration', ('collaboration',), 'Collaborations', False
    Live = 'Live Album', ('live album',), 'Live', False
    MixTape = 'MixTape', ('mixtape',), 'Other', False
    CoverAlbum = 'Cover Album', ('cover album', 'remake album'), 'Other', False
    Soundtrack = 'Soundtrack', ('soundtrack', 'ost'), 'Soundtracks', False
    Single = (
        'Single', ('single', 'song', 'digital single', 'promotional single', 'special single', 'other release'),
        'Singles', False
    )
    Album = 'Album', ('studio album', 'repackage album', 'full-length album', 'album'), 'Albums', True

    def __repr__(self):
        return f'<{type(self).__name__}: {self.value[0]!r}>'

    @classmethod
    def for_name(cls, name):
        if name:
            if isinstance(name, str):
                name = [name]
            for _name in name:
                _name = _name.lower().strip().replace('-', ' ').replace('_', ' ')
                for album_type in cls:
                    if any(cat in _name for cat in album_type.categories):
                        # log.debug(f'{name!r} => {album_type}')
                        return album_type
            log.debug(f'No DiscoEntryType exists for name={name!r}')
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
