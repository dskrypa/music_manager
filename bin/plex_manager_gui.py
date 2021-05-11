#!/usr/bin/env python

import sys
from pathlib import Path

THIS_PATH = Path(__file__).resolve()
sys.path.insert(0, THIS_PATH.parents[1].joinpath('lib').as_posix())
import _venv  # This will activate the venv, if it exists and is not already active

import logging

from ds_tools.argparsing import ArgParser
from ds_tools.core.main import wrap_main
from music.__version__ import __author_email__, __version__, __author__, __url__

log = logging.getLogger(__name__)


def parser():
    # fmt: off
    parser = ArgParser(description='Plex Manager GUI')
    parser.include_common_args('verbosity')
    # fmt: on
    return parser


@wrap_main
def main():
    args = parser().parse_args(req_subparser_value=False)

    from ds_tools.logging import init_logging
    init_logging(args.verbose, names=None, millis=True, set_levels={'PIL': 30})

    launch_gui(args)


def launch_gui(args):
    from music.common.prompts import set_ui_mode, UIMode
    from music.files.patches import apply_mutagen_patches
    from music.gui.patches import patch_all
    from music.gui.plex_views.main import PlexView

    apply_mutagen_patches()
    patch_all()
    set_ui_mode(UIMode.GUI)

    start_kwargs = dict(title='Plex Manager', resizable=True, size=(1700, 750), element_justification='center')
    PlexView.start(**start_kwargs)


if __name__ == '__main__':
    main()
