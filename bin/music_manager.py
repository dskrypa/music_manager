#!/usr/bin/env python

import os
import sys
from pathlib import Path

venv_path = Path(__file__).resolve().parents[1].joinpath('venv')
if not os.environ.get('VIRTUAL_ENV') and venv_path.exists():
    from subprocess import Popen
    os.environ.update(PYTHONHOME='', VIRTUAL_ENV=venv_path.as_posix())
    os.environ['PATH'] = '{}:{}'.format(venv_path.joinpath('Scripts').as_posix(), os.environ['PATH'])
    sys.exit(Popen([venv_path.joinpath('Scripts', 'python.exe').as_posix()] + sys.argv, env=os.environ).wait())

import logging

from ds_tools.argparsing import ArgParser
from ds_tools.logging import init_logging

sys.path.insert(0, Path(__file__).resolve().parents[1].joinpath('lib').as_posix())
from music.__version__ import __author_email__, __version__
from music.files import apply_mutagen_patches
from music.manager.file_info import (
    print_track_info, table_song_tags, table_tag_type_counts, table_unique_tag_values, print_processed_info
)
from music.manager.file_update import path_to_tag, update_tags_with_value, clean_tags
from music.manager.wiki_info import show_wiki_entity
from music.manager.wiki_match import show_matches
from music.manager.wiki_update import update_tracks

log = logging.getLogger(__name__)
apply_mutagen_patches()
SHOW_ARGS = {
    'info': 'Show track title, length, tag version, and tags', 'meta': 'Show track title, length, and tag version',
    'count': 'Count tracks by tag', 'table': 'Show tags in a table', 'unique': 'Count tracks with unique tag values',
    'processed': 'Show processed album info'
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
        if name == 'info':
            _parser.add_argument('--no_trim', '-T', action='store_true', help='Do not trim tag IDs')
        if name == 'processed':
            _parser.add_argument('--expand', '-x', action='count', default=0, help='Expand entities with a lot of nested info (may be specified multiple times to increase expansion level)')
            _parser.add_argument('--only_errors', '-E', action='store_true', help='Only print entries with processing errors')

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

    ws_parser = wiki_parser.add_subparser('sub_action', 'show', help='Show info about the entity with the given URL')
    ws_parser.add_argument('identifier', help='A wiki URL or title/name')
    ws_parser.add_argument('--expand', '-x', action='count', default=0, help='Expand entities with a lot of nested info (may be specified multiple times to increase expansion level)')
    ws_parser.add_argument('--limit', '-L', type=int, default=0, help='Maximum number of discography entry parts to show for a given album (default: unlimited)')
    ws_parser.add_argument('--types', '-t', nargs='+', help='Filter albums to only those that match the specified types')

    upd_parser = wiki_parser.add_subparser('sub_action', 'update', help='Update tracks in the given path(s) based on wiki info')
    upd_parser.add_argument('path', nargs='+', help='One or more paths of music files or directories containing music files')
    upd_parser.add_argument('--destination', '-d', metavar='PATH', help='Destination base directory for sorted files')
    upd_parser.add_argument('--url', '-u', help='A wiki URL (can only specify one file/directory when providing a URL)')
    upd_parser.add_argument('--soloist', '-S', action='store_true', help='For solo artists, use only their name instead of including their group, and do not sort them with their group')
    upd_parser.add_argument('--collab_mode', '-c', choices=('title', 'artist', 'both'), default='artist', help='List collaborators in the artist tag, the title tag, or both (default: %(default)s)')
    upd_parser.add_argument('--hide_edition', '-E', action='store_true', help='Exclude the edition from the album title, if present (default: include it)')

    match_parser = wiki_parser.add_subparser('sub_action', 'match', help='Match tracks in the given path(s) with wiki info')
    match_parser.add_argument('path', nargs='+', help='One or more paths of music files or directories containing music files')
    # endregion

    for _parser in (clean_parser, upd_parser):
        bpm_group = _parser.add_mutually_exclusive_group()
        bpm_group.add_argument('--bpm', '-b', action='store_true', default=None, help='Add a BPM tag if it is not already present (default: True if aubio is installed)')
        bpm_group.add_argument('--no_bpm', '-B', dest='bpm', action='store_false', help='Do not add a BPM tag if it is not already present')

    parser.include_common_args('verbosity', 'dry_run')
    return parser


def main():
    args = parser().parse_args()
    init_logging(args.verbose, log_path=None, names=None)
    # logging.getLogger('wiki_nodes.http.query').setLevel(logging.DEBUG)

    action, sub_action = args.action, getattr(args, 'sub_action', None)
    if action == 'show':
        if sub_action == 'info':
            print_track_info(args.path, args.tags, trim=not args.no_trim)
        elif sub_action == 'meta':
            print_track_info(args.path, meta_only=True)
        elif sub_action == 'count':
            table_tag_type_counts(args.path)
        elif sub_action == 'unique':
            table_unique_tag_values(args.path, args.tags)
        elif sub_action == 'table':
            table_song_tags(args.path, args.tags)
        elif sub_action == 'processed':
            print_processed_info(args.path, args.expand, args.only_errors)
        else:
            raise ValueError(f'Unexpected sub-action: {sub_action!r}')
    elif action == 'wiki':
        if sub_action == 'show':
            show_wiki_entity(args.identifier, args.expand, args.limit, args.types)
        elif sub_action == 'update':
            bpm = aubio_installed() if args.bpm is None else args.bpm
            update_tracks(
                args.path, args.dry_run, args.soloist, args.hide_edition, args.collab_mode, args.url, bpm,
                args.destination
            )
        elif sub_action == 'match':
            show_matches(args.path)
        else:
            raise ValueError(f'Unexpected sub-action: {sub_action!r}')
    elif action == 'path2tag':
        path_to_tag(args.path, args.dry_run, args.yes, args.title)
    elif action == 'update':
        update_tags_with_value(args.path, args.tag, args.value, args.replace, args.partial, args.dry_run)
    elif action == 'clean':
        bpm = aubio_installed() if args.bpm is None else args.bpm
        clean_tags(args.path, args.dry_run, bpm)
    else:
        raise ValueError(f'Unexpected action: {action!r}')


def aubio_installed():
    try:
        import aubio
    except ImportError:
        return False
    return True


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print()
