#!/usr/bin/env python

import sys
from pathlib import Path

THIS_PATH = Path(__file__).resolve()
sys.path.insert(0, THIS_PATH.parents[1].joinpath('lib').as_posix())
import _venv  # This will activate the venv, if it exists and is not already active

from music.cli.plex_manager_gui import PlexManagerGui


if __name__ == '__main__':
    PlexManagerGui.parse_and_run()
