#!/usr/bin/env python

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, PROJECT_ROOT.joinpath('bin').as_posix())
import _venv  # This will activate the venv, if it exists and is not already active

import logging
from datetime import date

from ds_tools.argparsing import ArgParser
from ds_tools.core import wrap_main
from ds_tools.logging import init_logging

sys.path.insert(0, PROJECT_ROOT.joinpath('lib').as_posix())
from music.__version__ import __author_email__, __version__
from music.files import apply_mutagen_patches
from music.manager.file_info import (
    print_track_info, table_song_tags, table_tag_type_counts, table_unique_tag_values, print_processed_info
)
from music.manager.file_update import path_to_tag, update_tags_with_value, clean_tags, remove_tags, add_track_bpm
from music.manager.images import extract_album_art, set_album_art, del_album_art
from music.manager.update import AlbumInfo
from music.manager.wiki_info import show_wiki_entity, pprint_wiki_page
from music.manager.wiki_match import show_matches, test_match
from music.manager.wiki_update import update_tracks

log = logging.getLogger(__name__)
apply_mutagen_patches()
DEFAULT_DEST_DIR = './sorted_{}'.format(date.today().strftime('%Y-%m-%d'))
SHOW_ARGS = {
    'info': 'Show track title, length, tag version, and tags', 'meta': 'Show track title, length, and tag version',
    'count': 'Count tracks by tag', 'table': 'Show tags in a table', 'unique': 'Count tracks with unique tag values',
    'processed': 'Show processed album info'
}


def parser():
    # fmt: off
    parser = ArgParser(description='Music Manager')

    # region File Actions
    with parser.add_subparser('action', 'show', help='Show song/tag information') as show_parser:
        for name, help_text in SHOW_ARGS.items():
            with show_parser.add_subparser('sub_action', name, help=help_text) as _parser:
                _parser.add_argument('path', nargs='*', default=['.'], help='Paths for music files or directories containing music files')
                if name in ('info', 'unique', 'table'):
                    _parser.add_argument('--tags', '-t', nargs='+', help='The tags to display', required=(name == 'unique'))
                if name == 'info':
                    _parser.add_argument('--no_trim', '-T', action='store_true', help='Do not trim tag IDs')
                if name == 'processed':
                    _parser.add_argument('--expand', '-x', action='count', default=0, help='Expand entities with a lot of nested info (may be specified multiple times to increase expansion level)')
                    _parser.add_argument('--only_errors', '-E', action='store_true', help='Only print entries with processing errors')

    with parser.add_subparser('action', 'path2tag', help='Update tags based on the path to each file') as p2t_parser:
        p2t_parser.add_argument('path', nargs='+', help='One or more paths of music files or directories containing music files')
        p2t_parser.add_argument('--title', '-t', action='store_true', help='Update title based on filename')
        p2t_parser.add_argument('--yes', '-y', action='store_true', help='Skip confirmation prompts')

    with parser.add_subparser('action', 'update', help='Set the value of the given tag on all music files in the given path') as set_parser:
        set_parser.add_argument('path', nargs='+', help='One or more paths of music files or directories containing music files')

        set_from_file = set_parser.add_argument_group('Load File Options', 'Options for loading updates from a file - may notbe combined with arguments from other option groups')
        set_from_file.add_argument('--load', '-L', metavar='PATH', help='Load updates from a json file (may not be combined with other options)')
        set_from_file.add_argument('--destination', '-d', metavar='PATH', default=DEFAULT_DEST_DIR, help='Destination base directory for sorted files (default: %(default)s)')

        set_from_args = set_parser.add_argument_group('Tag Update Options')
        set_from_args.add_argument('--tag', '-t', nargs='+', help='Tag ID(s) to modify (required)')
        set_from_args.add_argument('--value', '-V', help='Value to replace existing values with (required)')
        set_from_args.add_argument('--replace', '-r', nargs='+', help='If specified, only replace tag values that match the given patterns(s)')
        set_from_args.add_argument('--partial', '-p', action='store_true', help='Update only parts of tags that match a pattern specified via --replace/-r')

        set_parser.add_mutually_exclusive_arg_sets(set_from_file, set_from_args)

    with parser.add_subparser('action', 'clean', help='Clean undesirable tags from the specified files') as clean_parser:
        clean_parser.add_argument('path', nargs='+', help='One or more paths of music files or directories containing music files')
        bpm_group = clean_parser.add_mutually_exclusive_group()
        bpm_group.add_argument('--bpm', '-b', action='store_true', default=None, help='Add a BPM tag if it is not already present (default: True if aubio is installed)')
        bpm_group.add_argument('--no_bpm', '-B', dest='bpm', action='store_false', help='Do not add a BPM tag if it is not already present')

    with parser.add_subparser('action', 'remove', help='Remove the specified tags from the specified files') as rm_parser:
        rm_parser.add_argument('path', nargs='+', help='One or more paths of music files or directories containing music files')
        rm_group = rm_parser.add_mutually_exclusive_group()
        rm_group.add_argument('--tag', '-t', nargs='+', help='Tag ID(s) to remove')
        rm_group.add_argument('--all', '-A', action='store_true', help='Remove ALL tags')

    with parser.add_subparser('action', 'bpm', help='Add BPM info to the specified files') as bpm_parser:
        bpm_parser.add_argument('path', nargs='+', help='One or more paths of music files or directories containing music files')
        bpm_parser.include_common_args(parallel=4)
        # bpm_parser.add_argument('--parallel', '-P', type=int, default=1, help='Maximum number of workers to use in parallel (default: %(default)s)'))

    with parser.add_subparser('action', 'dump', help='Dump tag info about the specified files to json') as dump_parser:
        dump_parser.add_argument('path', help='A path for a music file or a directory containing music files')
        dump_parser.add_argument('output', help='The destination file path')
        dump_parser.add_argument('--title_case', '-T', action='store_true', help='Fix track and album names to use Title Case when they are all caps')

    with parser.add_subparser('action', 'cover', help='Extract or add cover art') as cover_parser:
        cover_parser.add_argument('path', help='A path for a music file or a directory containing music files')

        dump_cover_group = cover_parser.add_argument_group('Save Cover Options')
        dump_cover_group.add_argument('--save', '-s', metavar='PATH', help='Path to save the cover images from the specified file(s)')

        load_cover_group = cover_parser.add_argument_group('Load Cover Options')
        load_cover_group.add_argument('--load', '-L', metavar='PATH', help='Path to an image file')
        load_cover_group.add_argument('--max_width', '-w', type=int, default=1200, help='Resize the provided image if it is larger than this value')

        del_cover_group = cover_parser.add_argument_group('Save Cover Options')
        del_cover_group.add_argument('--remove', '-R', action='store_true', help='Remove all cover images')

        cover_parser.add_mutually_exclusive_arg_sets(dump_cover_group, load_cover_group, del_cover_group)
    # endregion

    with parser.add_subparser('action', 'wiki', help='Wiki matching / informational functions') as wiki_parser:
        with wiki_parser.add_subparser('sub_action', 'pprint', help='Pretty-print the parsed page content') as pp_parser:
            pp_parser.add_argument('url', help='A wiki entity URL')
            pp_parser.add_argument('--mode', '-m', choices=('content', 'processed', 'reprs', 'headers', 'raw'), default='content', help='Pprint mode (default: %(default)s)')

        with wiki_parser.add_subparser('sub_action', 'raw', help='Print the raw page content') as ppr_parser:
            ppr_parser.add_argument('url', help='A wiki entity URL')

        with wiki_parser.add_subparser('sub_action', 'show', help='Show info about the entity with the given URL') as ws_parser:
            ws_parser.add_argument('identifier', help='A wiki URL or title/name')
            ws_parser.add_argument('--expand', '-x', action='count', default=0, help='Expand entities with a lot of nested info (may be specified multiple times to increase expansion level)')
            ws_parser.add_argument('--limit', '-L', type=int, default=0, help='Maximum number of discography entry parts to show for a given album (default: unlimited)')
            ws_parser.add_argument('--types', '-t', nargs='+', help='Filter albums to only those that match the specified types')
            ws_parser.add_argument('--type', '-T', help='An EntertainmentEntity subclass to require that the given page matches')

        with wiki_parser.add_subparser('sub_action', 'update', help='Update tracks in the given path(s) based on wiki info') as upd_parser:
            upd_parser.add_argument('path', nargs='+', help='One or more paths of music files or directories containing music files')
            upd_parser.add_argument('--destination', '-d', metavar='PATH', default=DEFAULT_DEST_DIR, help='Destination base directory for sorted files (default: %(default)s)')
            upd_parser.add_argument('--url', '-u', help='A wiki URL (can only specify one file/directory when providing a URL)')
            upd_parser.add_argument('--soloist', '-S', action='store_true', help='For solo artists, use only their name instead of including their group, and do not sort them with their group')
            upd_parser.add_argument('--collab_mode', '-c', choices=('title', 'artist', 'both'), default='artist', help='List collaborators in the artist tag, the title tag, or both (default: %(default)s)')
            upd_parser.add_argument('--hide_edition', '-E', action='store_true', help='Exclude the edition from the album title, if present (default: include it)')
            upd_parser.add_argument('--title_case', '-T', action='store_true', help='Fix track and album names to use Title Case when they are all caps')
            upd_parser.add_argument('--artist', '-a', metavar='URL', help='Force the use of the given artist instead of an automatically discovered one')
            upd_parser.add_argument('--update_cover', '-C', action='store_true', help='Update the cover art for the album if it does not match an image in the matched wiki page')

            upd_sites = upd_parser.add_argument_group('Site Options').add_mutually_exclusive_group()
            upd_sites.add_argument('--sites', '-s', nargs='+', default=['kpop.fandom.com', 'www.generasia.com'], help='The wiki sites to search')
            upd_sites.add_argument('--all', '-A', action='store_const', const=None, dest='sites', help='Search all sites')
            upd_sites.add_argument('--ost', '-O', action='store_const', const=['wiki.d-addicts.com'], dest='sites', help='Search only wiki.d-addicts.com')

            bpm_group = upd_parser.add_argument_group('BPM Options').add_mutually_exclusive_group()
            bpm_group.add_argument('--bpm', '-b', action='store_true', default=None, help='Add a BPM tag if it is not already present (default: True if aubio is installed)')
            bpm_group.add_argument('--no_bpm', '-B', dest='bpm', action='store_false', help='Do not add a BPM tag if it is not already present')

            upd_data = upd_parser.add_argument_group('Track Data Options').add_mutually_exclusive_group()
            upd_data.add_argument('--dump', '-P', metavar='PATH', help='Dump track updates to a json file instead of updating the tracks')
            upd_data.add_argument('--load', '-L', metavar='PATH', help='Load track updates from a json file instead of from a wiki')

        with wiki_parser.add_subparser('sub_action', 'match', help='Match tracks in the given path(s) with wiki info') as match_parser:
            match_parser.add_argument('path', nargs='+', help='One or more paths of music files or directories containing music files')

        with wiki_parser.add_subparser('sub_action', 'test', help='Test matching of tracks in a given path with a given wiki URL') as test_parser:
            test_parser.add_argument('path', help='One path of music files or directories containing music files')
            test_parser.add_argument('url', help='A wiki URL for a page to test whether it matches the given files')

    parser.include_common_args('verbosity', 'dry_run')
    parser.add_common_sp_arg('--match_log', '-M', action='store_true', help='Enable debug logging for the album match processing logger')
    # fmt: on
    return parser


@wrap_main
def main():
    args = parser().parse_args(req_subparser_value=True)
    init_logging(args.verbose, log_path=None, names=None)
    # logging.getLogger('wiki_nodes.http.query').setLevel(logging.DEBUG)
    if args.match_log:
        logging.getLogger('music.manager.wiki_match.matching').setLevel(logging.DEBUG)

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
            show_wiki_entity(args.identifier, args.expand, args.limit, args.types, args.type)
        elif sub_action == 'update':
            bpm = aubio_installed() if args.bpm is None else args.bpm
            update_tracks(
                args.path, args.dry_run, args.soloist, args.hide_edition, args.collab_mode, args.url, bpm,
                args.destination, args.title_case, args.sites, args.dump, args.load, args.artist, args.update_cover
            )
        elif sub_action == 'match':
            show_matches(args.path)
        elif sub_action == 'pprint':
            pprint_wiki_page(args.url, args.mode)
        elif sub_action == 'test':
            test_match(args.path, args.url)
        elif sub_action == 'raw':
            pprint_wiki_page(args.url, 'raw')
        else:
            raise ValueError(f'Unexpected sub-action: {sub_action!r}')
    elif action == 'path2tag':
        path_to_tag(args.path, args.dry_run, args.yes, args.title)
    elif action == 'update':
        if args.load:
            AlbumInfo.load(args.load).update_and_move(dest_base_dir=Path(args.destination), dry_run=args.dry_run)
        else:
            if not args.tag or not args.value:
                raise ValueError(f'Both --tag/-t and --value/-V are required')
            update_tags_with_value(args.path, args.tag, args.value, args.replace, args.partial, args.dry_run)
    elif action == 'clean':
        bpm = aubio_installed() if args.bpm is None else args.bpm
        clean_tags(args.path, args.dry_run, bpm)
    elif action == 'remove':
        if not args.tag and not args.all:
            raise ValueError('Either --tag/-t or --all/-A must be provided')
        remove_tags(args.path, args.tag, args.dry_run, args.all)
    elif action == 'bpm':
        add_track_bpm(args.path, args.parallel, args.dry_run)
    elif action == 'dump':
        AlbumInfo.from_path(args.path).dump(args.output, args.title_case)
    elif action == 'cover':
        if args.save:
            extract_album_art(args.path, args.save)
        elif args.load:
            set_album_art(args.path, args.load, args.max_width, args.dry_run)
        elif args.remove:
            del_album_art(args.path, args.dry_run)
    else:
        raise ValueError(f'Unexpected action: {action!r}')


def aubio_installed():
    try:
        import aubio
    except ImportError:
        return False
    return True


if __name__ == '__main__':
    main()
