#!/usr/bin/env python
"""
Manage music files

:author: Doug Skrypa
"""

import logging
import sys
from pathlib import Path

from ds_tools.argparsing import ArgParser
from ds_tools.logging import init_logging

sys.path.insert(0, Path(__file__).resolve().parents[1].joinpath('lib').as_posix())
from music_manager.files import apply_mutagen_patches
from music_manager.files.info import print_track_info, table_song_tags, table_tag_type_counts, table_unique_tag_values
from music_manager.files.update import path_to_tag, update_tags

log = logging.getLogger(__name__)
apply_mutagen_patches()
SHOW_ARGS = {
    'info': 'Show track title, length, tag version, and tags', 'meta': 'Show track title, length, and tag version',
    'count': 'Count tracks by tag', 'table': 'Show tags in a table', 'unique': 'Count tracks with unique tag values'
}


def parser():
    parser = ArgParser(description='Music Manager')

    show_parser = parser.add_subparser('action', 'show', help='Show song/tag information')
    for name, help_text in SHOW_ARGS.items():
        _parser = show_parser.add_subparser('sub_action', name, help=help_text)
        _parser.add_argument('path', nargs='+', help='Paths for music files or directories containing music files')
        if name in ('info', 'unique', 'table'):
            _parser.add_argument('--tags', '-t', nargs='+', help='The tags to display', required=(name == 'unique'))

    p2t_parser = parser.add_subparser('action', 'path2tag', help='Update tags based on the path to each file')
    p2t_parser.add_argument('path', nargs='+', help='One or more paths of music files or directories containing music files')
    p2t_parser.add_argument('--title', '-t', action='store_true', help='Update title based on filename')
    p2t_parser.add_argument('--yes', '-y', action='store_true', help='Skip confirmation prompts')

    set_parser = parser.add_subparser('action', 'update', help='Set the value of the given tag on all music files in the given path')
    set_parser.add_argument('path', nargs='+', help='One or more paths of music files or directories containing music files')
    set_parser.add_argument('--tag', '-t', nargs='+', help='Tag ID(s) to modify', required=True)
    set_parser.add_argument('--value', '-V', help='Value to replace existing values with', required=True)
    set_parser.add_argument('--replace', '-r', nargs='+', help='If specified, only replace tag values that match the given patterns(s)')
    set_parser.add_argument('--partial', '-p', action='store_true', help='Update only parts of tags that match a pattern specified via --replace/-r')

    parser.include_common_args('verbosity', 'dry_run')
    return parser


def main():
    args = parser().parse_args()
    init_logging(args.verbose, log_path=None)

    if args.action == 'show':
        sub_action = args.sub_action
        if sub_action == 'info':
            print_track_info(args.path, args.tags)
        elif sub_action == 'meta':
            print_track_info(args.path, meta_only=True)
        elif sub_action == 'count':
            table_tag_type_counts(args.path)
        elif sub_action == 'unique':
            table_unique_tag_values(args.path, args.tags)
        elif sub_action == 'table':
            table_song_tags(args.path, args.tags)
    elif args.action == 'path2tag':
        path_to_tag(args.path, args.dry_run, args.yes, args.title)
    elif args.action == 'set':
        update_tags(args.path, args.tag, args.value, args.replace, args.partial, args.dry_run)
    else:
        log.error(f'Unexpected action: {args.action!r}')


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print()
