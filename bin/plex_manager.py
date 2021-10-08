#!/usr/bin/env python
# PYTHON_ARGCOMPLETE_OK

import sys
from pathlib import Path

sys.path.insert(0, Path(__file__).resolve().parents[1].joinpath('lib').as_posix())
import _venv  # This will activate the venv, if it exists and is not already active

from music.cli.plex_manager import main


if __name__ == '__main__':
    main()
