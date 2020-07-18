#!/usr/bin/env python

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, PROJECT_ROOT.joinpath('bin').as_posix())
import _venv  # This will activate the venv, if it exists and is not already active

from ds_tools.argparsing import ArgParser
from ds_tools.core import wrap_main
from ds_tools.logging import init_logging

# sys.path.insert(0, 'C:/Users/dougs/git/pymobiledevice')
sys.path.insert(0, PROJECT_ROOT.joinpath('lib').as_posix())
from music.__version__ import __author_email__, __version__
from music.shell import iPodShell


def parser():
    parser = ArgParser(description='iPod Shell')
    parser.include_common_args('verbosity')
    return parser


@wrap_main
def main():
    args = parser().parse_args()
    init_logging(args.verbose or 1, log_path=None, names=None)

    iPodShell().cmdloop()


if __name__ == '__main__':
    main()
