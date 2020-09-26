#!/usr/bin/env python

import sys
from pathlib import Path

sys.path.insert(0, Path(__file__).resolve().parents[1].joinpath('lib').as_posix())
import _venv  # This will activate the venv, if it exists and is not already active

from ds_tools.argparsing import ArgParser

from pypod.shell import iDeviceShell
from music.__version__ import __author_email__, __version__


def parser():
    parser = ArgParser(description='iPod Shell')
    parser.include_common_args('verbosity')
    return parser


def main():
    args = parser().parse_args()

    from ds_tools.logging import init_logging
    init_logging(args.verbose or 1, log_path=None, names=None)

    from music import ipod_shell_cmds  # Necessary to load them
    iDeviceShell().cmdloop()


if __name__ == '__main__':
    main()
