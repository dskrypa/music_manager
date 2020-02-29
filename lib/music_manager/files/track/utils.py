"""
:author: Doug Skrypa
"""

__all__ = ['MusicFileProperty', 'RATING_RANGES', 'TYPED_TAG_MAP']

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


class MusicFileProperty:
    def __init__(self, name):
        self.name = '_{}#{}'.format(self.__class__.__name__, name)
        self.parts = name.split('.')

    def __get__(self, obj, owner):
        if obj is None:
            return self
        try:
            value = obj.__dict__[self.name]
        except KeyError:
            value = obj._f
            for part in self.parts:
                value = getattr(value, part)
            obj.__dict__[self.name] = value
        return value
