"""
:author: Doug Skrypa
"""

import shutil
from pathlib import Path

__all__ = ['deinit_colorama', 'can_add_bpm', 'find_ffmpeg']


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
