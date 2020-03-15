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
from music.files import apply_mutagen_patches
from music.manager.file_info import print_track_info, table_song_tags, table_tag_type_counts, table_unique_tag_values
from music.manager.file_update import path_to_tag, update_tags_with_value, clean_tags
from music.manager.wiki_info import show_wiki_entity

log = logging.getLogger(__name__)
apply_mutagen_patches()
SHOW_ARGS = {
    'info': 'Show track title, length, tag version, and tags', 'meta': 'Show track title, length, and tag version',
    'count': 'Count tracks by tag', 'table': 'Show tags in a table', 'unique': 'Count tracks with unique tag values'
}


def parser():
    parser = ArgParser(description='Music Manager')

    # region File Actions
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

    clean_parser = parser.add_subparser('action', 'clean', help='Clean undesirable tags from the specified files')
    clean_parser.add_argument('path', nargs='+', help='One or more paths of music files or directories containing music files')
    # endregion

    # region Wiki Actions
    wiki_parser = parser.add_subparser('action', 'wiki', help='Wiki matching / informational functions')

    url_parser = wiki_parser.add_subparser('sub_action', 'show', help='Show info about the entity with the given URL')
    url_parser.add_argument('url', help='A wiki URL')
    # endregion

    parser.include_common_args('verbosity', 'dry_run')
    return parser


def main():
    args = parser().parse_args()
    init_logging(args.verbose, log_path=None, names=None)

    action, sub_action = args.action, getattr(args, 'sub_action', None)
    if action == 'show':
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
        else:
            raise ValueError(f'Unexpected sub-action: {sub_action!r}')
    elif action == 'wiki':
        if sub_action == 'show':
            show_wiki_entity(args.url)
        else:
            raise ValueError(f'Unexpected sub-action: {sub_action!r}')
    elif action == 'path2tag':
        path_to_tag(args.path, args.dry_run, args.yes, args.title)
    elif action == 'update':
        update_tags_with_value(args.path, args.tag, args.value, args.replace, args.partial, args.dry_run)
    elif action == 'clean':
        clean_tags(args.path, args.dry_run)
    else:
        raise ValueError(f'Unexpected action: {action!r}')


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print()
