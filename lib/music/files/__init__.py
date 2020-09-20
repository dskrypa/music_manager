"""
:author: Doug Skrypa
"""

from importlib import import_module

__attr_module_map = {
    # exceptions
    'InvalidAlbumDir': 'exceptions',
    'InvalidTagName': 'exceptions',
    'TagException': 'exceptions',
    'TagNotFound': 'exceptions',
    'TagValueException': 'exceptions',
    'UnsupportedTagForFileType': 'exceptions',
    # track
    'SongFile': 'track',
    'tag_repr': 'track',
    'iter_music_files': 'track',
    # album
    'AlbumDir': 'album',
    'iter_album_dirs': 'album',
    'iter_albums_or_files': 'album',
}

# noinspection PyUnresolvedReferences
__all__ = ['album', 'changes', 'exceptions', 'parsing', 'patches', 'paths', 'track']
__all__.extend(__attr_module_map.keys())


def __dir__():
    return sorted(__all__ + list(globals().keys()))


def __getattr__(name):
    try:
        module_name = __attr_module_map[name]
    except KeyError:
        raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
    else:
        module = import_module(f'.{module_name}', __name__)
        return getattr(module, name)
