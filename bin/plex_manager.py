#!/usr/bin/env python
# TODO: # PYTHON_ARGCOMPLETE_OK

import sys
from pathlib import Path

sys.path.insert(0, Path(__file__).resolve().parents[1].joinpath('lib').as_posix())
import _venv  # This will activate the venv, if it exists and is not already active

from music.cli.plex_manager import PlexManager


if __name__ == '__main__':
    PlexManager.parse_and_run()
