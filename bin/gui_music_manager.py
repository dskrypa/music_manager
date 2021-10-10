#!/usr/bin/env python

import sys
from pathlib import Path

THIS_PATH = Path(__file__).resolve()
sys.path.insert(0, THIS_PATH.parents[1].joinpath('lib').as_posix())
import _venv  # This will activate the venv, if it exists and is not already active

from music.__version__ import __author_email__, __version__, __author__, __url__  # noqa
from music.cli.gui_music_manager import main


if __name__ == '__main__':
    main()
