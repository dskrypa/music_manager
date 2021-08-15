#!/usr/bin/env python

import sys
from pathlib import Path

THIS_PATH = Path(__file__).resolve()
sys.path.insert(0, THIS_PATH.parents[1].joinpath('lib').as_posix())
import _venv  # This will activate the venv, if it exists and is not already active

import logging

from ds_tools.argparsing import ArgParser
from ds_tools.core.main import wrap_main
from music.gui.popups.image import ClockView
from music.__version__ import __author_email__, __version__, __author__, __url__

log = logging.getLogger(__name__)


def parser():
    parser = ArgParser(description='Clock')
    parser.add_argument('--no_seconds', '-S', dest='seconds', action='store_false', help='Hide seconds')
    parser.include_common_args('verbosity')
    return parser


@wrap_main
def main():
    args = parser().parse_args(req_subparser_value=False)

    from ds_tools.logging import init_logging
    init_logging(args.verbose, names=None, millis=True, set_levels={'PIL': 30})

    ClockView(seconds=args.seconds).get_result()


if __name__ == '__main__':
    main()
