#!/usr/bin/env python

import sys
from pathlib import Path

sys.path.insert(0, Path(__file__).resolve().parents[1].joinpath('lib').as_posix())
import _venv  # This will activate the venv, if it exists and is not already active

import logging

from ds_tools.argparsing import ArgParser
from ds_tools.core.main import wrap_main
from music.__version__ import __author_email__, __version__, __author__, __url__

log = logging.getLogger(__name__)


def parser():
    # fmt: off
    parser = ArgParser(description='Music Manager GUI')
    parser.include_common_args('verbosity')
    parser.add_common_sp_arg('--match_log', action='store_true', help='Enable debug logging for the album match processing logger')
    # fmt: on
    return parser


@wrap_main
def main():
    args = parser().parse_args()

    from ds_tools.logging import init_logging
    init_logging(args.verbose, log_path=None, names=None)

    from music.files.patches import apply_mutagen_patches
    from music.gui.patches import patch_all
    apply_mutagen_patches()
    patch_all()

    # logging.getLogger('wiki_nodes.http.query').setLevel(logging.DEBUG)
    if args.match_log:
        logging.getLogger('music.manager.wiki_match.matching').setLevel(logging.DEBUG)

    from PySimpleGUI import theme
    theme('SystemDefaultForReal')

    from music.gui.views.base import ViewManager
    from music.gui.views.main import MainView
    ViewManager(title='Music Manager', resizable=True, size=(1500, 750))(MainView)


if __name__ == '__main__':
    main()
