"""
:author: Doug Skrypa
"""

import shutil
from pathlib import Path

__all__ = ['MissingMixin', 'deinit_colorama', 'can_add_bpm', 'find_ffmpeg', 'format_duration']


def deinit_colorama():
    try:
        import colorama
        import atexit
    except ImportError:
        pass
    else:
        colorama.deinit()
        atexit.unregister(colorama.initialise.reset_all)


def can_add_bpm():
    try:
        import aubio
        import ffmpeg
        import numpy
    except ImportError:
        return False
    return bool(find_ffmpeg())


def find_ffmpeg():
    for path in (None, Path('~/sbin/ffmpeg/bin').expanduser(), Path('~/bin/ffmpeg/bin').expanduser()):
        if ffmpeg := shutil.which('ffmpeg', path=path):
            return ffmpeg
    return None


def format_duration(seconds: float) -> str:
    """
    Formats time in seconds as (Dd)HH:MM:SS (time.stfrtime() is not useful for formatting durations).

    :param seconds: Number of seconds to format
    :return: Given number of seconds as (Dd)HH:MM:SS
    """
    x = '-' if seconds < 0 else ''
    m, s = divmod(abs(seconds), 60)
    h, m = divmod(int(m), 60)
    d, h = divmod(h, 24)
    x = f'{x}{d}d' if d > 0 else x
    return f'{x}{h:02d}:{m:02d}:{s:02d}' if isinstance(s, int) else f'{x}{h:02d}:{m:02d}:{s:05.2f}'


class MissingMixin:
    @classmethod
    def _missing_(cls, value):
        if isinstance(value, str):
            try:
                return cls._member_map_[value.upper()]  # noqa
            except KeyError:
                pass
        return super()._missing_(value)  # noqa
