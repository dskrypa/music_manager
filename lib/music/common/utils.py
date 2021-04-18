"""
:author: Doug Skrypa
"""

import shutil
from pathlib import Path

__all__ = ['stars', 'deinit_colorama', 'can_add_bpm', 'find_ffmpeg']


def stars(rating, out_of=10, num_stars=5, chars=('\u2605', '\u2730'), half='\u00BD'):
    if out_of < 1:
        raise ValueError('out_of must be > 0')

    filled, remainder = map(int, divmod(num_stars * rating, out_of))
    if half and remainder:
        empty = num_stars - filled - 1
        mid = half
    else:
        empty = num_stars - filled
        mid = ''
    a, b = chars
    return (a * filled) + mid + (b * empty)


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
