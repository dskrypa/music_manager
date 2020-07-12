#!/usr/bin/env python

from _venv import maybe_activate_venv
maybe_activate_venv()

import sys
from pathlib import Path

from ds_tools.argparsing import ArgParser
from ds_tools.core import wrap_main
from ds_tools.logging import init_logging

sys.path.insert(0, Path(__file__).resolve().parents[1].joinpath('lib').as_posix())
from music.__version__ import __author_email__, __version__
from music.ipod.shell import iPodShell


def parser():
    parser = ArgParser(description='iPod Shell')
    parser.include_common_args('verbosity')
    return parser


@wrap_main
def main():
    args = parser().parse_args()
    init_logging(args.verbose, log_path=None, names=None)

    iPodShell().cmdloop()


if __name__ == '__main__':
    main()
