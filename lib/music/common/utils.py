"""
:author: Doug Skrypa
"""

__all__ = ['stars', 'deinit_colorama', 'aubio_installed']


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


def aubio_installed():
    try:
        import aubio
    except ImportError:
        return False
    return True
