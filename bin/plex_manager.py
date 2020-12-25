#!/usr/bin/env python
# PYTHON_ARGCOMPLETE_OK

import sys
from pathlib import Path

sys.path.insert(0, Path(__file__).resolve().parents[1].joinpath('lib').as_posix())
import _venv  # This will activate the venv, if it exists and is not already active

import argparse
import logging
from typing import TYPE_CHECKING, Iterable, Tuple, Dict

from ds_tools.argparsing import ArgParser
from ds_tools.core.main import wrap_main
from ds_tools.output.constants import PRINTER_FORMATS
from music.__version__ import __author_email__, __version__

if TYPE_CHECKING:
    from plexapi.audio import Track
    from music.plex.typing import PlexObjTypes

log = logging.getLogger(__name__)


def parser():
    parser = ArgParser(description='Plex Manager\n\nYou will be securely prompted for your password for the first login, after which a session token will be cached')

    with parser.add_subparser('action', 'sync', help='Sync Plex information') as sync_parser:
        ratings_parser = sync_parser.add_subparser('sync_action', 'ratings', help='Sync song rating information between Plex and files')
        ratings_parser.add_argument('direction', choices=('to_files', 'from_files'), help='Direction to sync information')
        ratings_parser.add_argument('--path_filter', '-f', help='If specified, paths that will be synced must contain the given text (not case sensitive)')

        playlists_parser = sync_parser.add_subparser('sync_action', 'playlists', help='Sync playlists with custom filters')

    obj_types = ('track', 'artist', 'album', 'tracks', 'artists', 'albums')
    ops = (
        'contains, endswith, exact, exists, gt, gte, icontains, iendswith, iexact, in, iregex, istartswith, like, lt, '
        'lte, ne, regex, startswith'
    )

    with parser.add_subparser('action', 'find', help='Find Plex information') as find_parser:
        find_parser.add_argument('obj_type', choices=obj_types, help='Object type')
        find_parser.add_argument('title', nargs='*', default=None, help='Object title (optional)')
        find_parser.add_argument('--escape', '-e', default='()', help='Escape the provided regex special characters (default: %(default)r)')
        find_parser.add_argument('--allow_inst', '-I', action='store_true', help='Allow search results that include instrumental versions of songs')
        find_parser.add_argument('--full_info', '-F', action='store_true', help='Print all available info about the discovered objects')
        find_parser.add_argument('--format', '-f', choices=PRINTER_FORMATS, default='yaml', help='Output format to use for --full_info (default: %(default)s)')
        find_parser.add_argument('query', nargs=argparse.REMAINDER, help=f'Query in the format --field[__operation] value; valid operations: {ops}')

    with parser.add_subparser('action', 'rate', help='Update ratings in Plex') as rate_parser:
        rate_parser.add_argument('obj_type', choices=obj_types, help='Object type')
        rate_parser.add_argument('rating', type=int, help='Rating out of 10')
        rate_parser.add_argument('title', nargs='*', default=None, help='Object title (optional)')
        rate_parser.add_argument('--escape', '-e', default='()', help='Escape the provided regex special characters (default: %(default)r)')
        rate_parser.add_argument('--allow_inst', '-I', action='store_true', help='Allow search results that include instrumental versions of songs')
        rate_parser.add_argument('query', nargs=argparse.REMAINDER, help=f'Query in the format --field[__operation] value; valid operations: {ops}')

    parser.add_common_sp_arg('--server_path_root', '-r', metavar='PATH', help='The root of the path to use from this computer to generate paths to files from the path used by Plex.  When you click on the "..." for a song in Plex and click "Get Info", there will be a path in the "Files" box - for example, "/media/Music/a_song.mp3".  If you were to access that file from this computer, and the path to that same file is "//my_nas/media/Music/a_song.mp3", then the server_path_root would be "//my_nas/" (only needed when not already cached)')
    parser.add_common_sp_arg('--server_url', '-u', metavar='URL', help='The proto://host:port to use to connect to your local Plex server - for example: "https://10.0.0.100:12000" (only needed when not already cached)')
    parser.add_common_sp_arg('--username', '-n', help='Plex username (only needed when a token is not already cached)')
    parser.add_common_sp_arg('--config_path', '-c', metavar='PATH', default='~/.config/plexapi/config.ini', help='Config file in which your token and server_path_root / server_url are stored (default: %(default)s)')
    parser.add_common_sp_arg('--music_library', '-m', default=None, help='Name of the Music library to use (default: Music)')

    parser.include_common_args('verbosity', 'dry_run')
    return parser


@wrap_main
def main():
    args, dynamic = parser().parse_with_dynamic_args('query')

    from ds_tools.logging import init_logging
    init_logging(args.verbose, log_path=None, names=None, millis=True)

    from music.files.patches import apply_mutagen_patches
    apply_mutagen_patches()

    from music.plex import LocalPlexServer
    plex = LocalPlexServer(
        args.server_url, args.username, args.server_path_root, args.config_path, args.music_library, args.dry_run
    )

    if args.action == 'sync':
        if args.sync_action == 'ratings':
            if args.direction == 'to_files':
                plex.sync_ratings_to_files(args.path_filter)
            elif args.direction == 'from_files':
                plex.sync_ratings_from_files(args.path_filter)
            else:
                log.error('Unconfigured direction')
        elif args.sync_action == 'playlists':
            kpop_tracks = plex.query('track', genre__like_exact='[kj]-?pop')
            plex.sync_playlist(
                'K-Pop Female Solo Artists 3\u00BD+ Stars',
                query=kpop_tracks.filter(
                    userRating__gte=7,
                    grandparentTitle__like='taeyeon|chungha|younha|heize|rothy|sunmi|ailee'
                )
            )
            plex.sync_playlist('K-Pop ALL', query=kpop_tracks)
            plex.sync_playlist('K-Pop 1 Star', query=kpop_tracks.filter(userRating=2))
            plex.sync_playlist('K-Pop 2 Stars', query=kpop_tracks.filter(userRating=4))
            plex.sync_playlist('K-Pop 3 Stars', query=kpop_tracks.filter(userRating=6))
            plex.sync_playlist('K-Pop 3+ Stars', query=kpop_tracks.filter(userRating__gte=6))
            plex.sync_playlist('K-Pop 3\u00BD Stars', query=kpop_tracks.filter(userRating=7))
            plex.sync_playlist('K-Pop 3\u00BD+ Stars', query=kpop_tracks.filter(userRating__gte=7))
            plex.sync_playlist('K-Pop 4 Stars', query=kpop_tracks.filter(userRating=8))
            plex.sync_playlist('K-Pop 4+ Stars', query=kpop_tracks.filter(userRating__gte=8))
            plex.sync_playlist('K-Pop 4~4\u00BD Stars', query=kpop_tracks.filter(userRating__gte=8, userRating__lte=9))
            plex.sync_playlist('K-Pop 4\u00BD Stars', query=kpop_tracks.filter(userRating=9))
            plex.sync_playlist('K-Pop 5 Stars', query=kpop_tracks.filter(userRating__gte=10))
            plex.sync_playlist(
                'K-Pop Unrated',
                query=kpop_tracks.filter(
                    userRating=0,
                    genre__like_exact='k-?pop',
                    genre__not_like='christmas',
                    title__not_like=r'(?:^|\()(?:intro|outro)(?:$|\s|:|\))|\(inst(?:\.?|rumental)|(?:japanese|jp|karaoke|mandarin|chinese) ver(?:\.|sion)|christmas|santa|remix|snow',
                    parentTitle__not_like='christmas|santa',
                    duration__gte=60000,
                ).unique()
            )
            plex.sync_playlist(
                'K-Pop Unrated from Known Artists',
                query=kpop_tracks.filter(userRating__gte=7).artists().tracks().filter(
                    userRating=0,
                    genre__like_exact='k-?pop',
                    genre__not_like='christmas',
                    title__not_like=r'(?:^|\()(?:intro|outro)(?:$|\s|:|\))|\(inst(?:\.?|rumental)|(?:japanese|jp|karaoke|mandarin|chinese) ver(?:\.|sion)|christmas|santa|remix|snow',
                    parentTitle__not_like='christmas|santa',
                    duration__gte=60000,
                ).unique()
            )
        else:
            log.error('Unconfigured sync action')
    elif args.action == 'find':
        from ds_tools.output import bullet_list, Printer

        p = Printer(args.format)
        obj_type, kwargs = parse_filters(args.obj_type, args.title, dynamic, args.escape, args.allow_inst)
        objects = plex.find_objects(obj_type, **kwargs)  # type: Iterable[Track]
        if objects:
            if args.full_info:
                p.pprint({repr(obj): obj.as_dict() for obj in objects})
                # for obj in objects:
                #     print(f'{obj.artist().title}\t{obj.album().title}\t{obj.title}\t{obj.userRating}')
            else:
                print(bullet_list(objects))
        else:
            log.warning('No results.')
    elif args.action == 'rate':
        from music.common.utils import stars
        if args.rating < 0 or args.rating > 10:
            raise ValueError('Ratings must be between 0 and 10')
        obj_type, kwargs = parse_filters(args.obj_type, args.title, dynamic, args.escape, args.allow_inst)
        objects = plex.find_objects(obj_type, **kwargs)
        if not objects:
            log.warning('No results.')
        else:
            prefix = '[DRY RUN] Would update' if args.dry_run else 'Updating'
            for obj in objects:
                if obj.userRating == args.rating:
                    log.info('No changes necessary for {}'.format(obj))
                else:
                    log.info('{} {}\'s rating => {}'.format(prefix, obj, stars(args.rating)))
                    if not args.dry_run:
                        obj.edit(**{'userRating.value': args.rating})
    else:
        log.error('Unconfigured action')


def parse_filters(obj_type, title, filters, escape, allow_inst) -> Tuple['PlexObjTypes', Dict[str, str]]:
    """
    :param str obj_type: Type of Plex object to find (tracks, albums, artists, etc)
    :param list title: Parts of the name of the object(s) to find, if searching by title__like2
    :param dict filters: Additional filters to apply during the search
    :param escape: Characters that should be escaped instead of treated as special regex characters
    :param bool allow_inst: Allow search results that include instrumental versions of songs
    :return tuple: (str(normalized object type), dict(filters))
    """
    obj_type = obj_type[:-1] if obj_type.endswith('s') else obj_type
    escape_tbl = str.maketrans({c: '\\' + c for c in '()[]{}^$+*.?|\\' if c in escape})
    regexcape = lambda text: text.translate(escape_tbl)
    title = regexcape(' '.join(title)) if title else None

    for key, val in filters.items():
        try:
            op = key.rsplit('__', 1)[1]
        except Exception:
            pass
        else:
            if op in ('regex', 'iregex', 'like', 'like_exact', 'not_like'):
                filters[key] = regexcape(val)

    if title:
        filters.setdefault('title__like', title)

    if not allow_inst:
        filters.setdefault('title__not_like', 'inst(?:\.?|rumental)')

    log.debug('obj_type={}, title={!r} => query={}'.format(obj_type, title, filters))
    # noinspection PyTypeChecker
    return obj_type, filters


if __name__ == '__main__':
    main()
