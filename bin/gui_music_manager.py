#!/usr/bin/env python

r"""
How to add to right-click context menu - Windows:
    Computer\HKEY_CLASSES_ROOT\Directory\shell\Update Album Tags\command
    C:\Users\dougs\git\ds_tools\venv\Scripts\python.exe "C:\Users\dougs\git\music_manager\bin\gui_music_manager.py" open "%1" -vv
"""
# TODO: Add easy clean all / add bpm right-click action

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
    with parser.add_subparser('action', 'open', help='Open directly to the Album view for the given path') as open_parser:
        open_parser.add_argument('album_path', help='The path to the album to open')
    with parser.add_subparser('action', 'clean', help='Open directly to the Clean view for the given path') as clean_parser:
        clean_parser.add_argument('path', help='The directory containing files to clean')
    parser.include_common_args('verbosity')
    parser.add_common_sp_arg('--match_log', action='store_true', help='Enable debug logging for the album match processing logger')
    # fmt: on
    return parser


@wrap_main
def main():
    args = parser().parse_args()

    from ds_tools.logging import init_logging
    init_logging(args.verbose, names=None, millis=True)

    from music.files.patches import apply_mutagen_patches
    from music.gui.patches import patch_all
    apply_mutagen_patches()
    patch_all()

    # logging.getLogger('wiki_nodes.http.query').setLevel(logging.DEBUG)
    if args.match_log:
        logging.getLogger('music.manager.wiki_match.matching').setLevel(logging.DEBUG)

    from music.common.prompts import set_ui_mode, UIMode
    set_ui_mode(UIMode.GUI)

    from PySimpleGUI import theme
    theme('SystemDefaultForReal')

    start_kwargs = dict(title='Music Manager', resizable=True, size=(1700, 750), element_justification='center')
    if args.action == 'clean':
        from music.gui.views.clean import CleanView
        # TODO: Make CleanView support any path rather than an AlbumDir
        # CleanView.start({'path': args.path}, **start_kwargs)
    elif args.action == 'open':
        from music.gui.views.album import AlbumView
        from music.files.album import AlbumDir
        AlbumView.start({'album': AlbumDir(args.album_path)}, **start_kwargs)
    else:
        from music.gui.views.main import MainView
        MainView.start(**start_kwargs)


if __name__ == '__main__':
    main()
