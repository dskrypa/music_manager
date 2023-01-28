#!/usr/bin/env python

from _venv_helper import import_main

main = import_main(__file__, 'music_gui.cli')
from music.__version__ import __author_email__, __version__, __author__, __url__  # noqa


if __name__ == '__main__':
    main()
