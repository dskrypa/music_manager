# PYTHON_ARGCOMPLETE_OK

import argparse
import logging
from typing import TYPE_CHECKING, Iterable

from ..__version__ import __author_email__, __version__  # noqa
from ds_tools.argparsing import ArgParser
from ds_tools.core.main import wrap_main
from ds_tools.output.constants import PRINTER_FORMATS

if TYPE_CHECKING:
    from plexapi.audio import Track

log = logging.getLogger(__name__)


def parser():
    description = (
        'Plex Manager\n\nYou will be securely prompted for your password for the first login, after which a session'
        ' token will be cached'
    )
    parser = ArgParser(description=description)

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

    with parser.add_subparser('action', 'rate_offset', help='Update all track ratings in Plex with an offset') as rate_offset_parser:
        rate_offset_parser.add_argument('--min_rating', '-min', type=int, default=2, help='Minimum rating for which a change will be made')
        rate_offset_parser.add_argument('--max_rating', '-max', type=int, default=10, help='Maximum rating for which a change will be made')
        rate_offset_parser.add_argument('--offset', '-o', type=int, default=-1, help='Adjustment to make')

    with parser.add_subparser('action', 'playlist', help='Save or compare playlists') as playlist_parser:
        with playlist_parser.add_subparser('sub_action', 'dump', help='Save playlists') as playlist_dump:
            playlist_dump.add_argument('path', help='Location to write the playlist dump')
            playlist_dump.add_argument('--playlist', '-p', help='Dump the specified playlist (default: all)')
        with playlist_parser.add_subparser('sub_action', 'compare', help='Compare playlists') as playlist_cmp:
            playlist_cmp.add_argument('path', help='Location of the playlist dump to compare')
            playlist_cmp.add_argument('--playlist', '-p', help='Compare the specified playlist (default: all)')
            playlist_cmp.add_argument('--strict', '-s', action='store_true', help='Perform a strict comparison (default: by artist/album/title)')
        with playlist_parser.add_subparser('sub_action', 'list', help='List playlists in a dump') as playlist_list:
            playlist_list.add_argument('path', help='Location of the playlist dump to read')

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
            from music.plex.ratings import sync_ratings
            sync_ratings(plex, args.direction, args.path_filter)
        elif args.sync_action == 'playlists':
            sync_playlists(plex)
        else:
            raise ValueError(f'Invalid sync action={args.sync_action!r}')
    elif args.action == 'find':
        find_and_print(
            plex, args.format, args.obj_type, args.title, dynamic, args.escape, args.allow_inst, args.full_info
        )
    elif args.action == 'rate':
        from music.plex.ratings import find_and_rate
        find_and_rate(plex, args.rating, args.obj_type, args.title, dynamic, args.escape, args.allow_inst)
    elif args.action == 'rate_offset':
        from music.plex.ratings import adjust_track_ratings
        adjust_track_ratings(plex, args.min_rating, args.max_rating, args.offset)
    elif args.action == 'playlist':
        from music.plex.playlist import dump_playlists, compare_playlists, list_playlists
        if args.sub_action == 'dump':
            dump_playlists(plex, args.path, args.playlist)
        elif args.sub_action == 'compare':
            compare_playlists(plex, args.path, args.playlist, args.strict)
        elif args.sub_action == 'list':
            list_playlists(plex, args.path)
        else:
            log.error(f'Invalid playlist action={args.sub_action!r}')
    else:
        log.error(f'Invalid action={args.action!r}')


def find_and_print(plex, fmt, obj_type, title, dynamic, escape, allow_inst, full_info):
    from ds_tools.output import bullet_list, Printer
    from music.plex.utils import parse_filters

    p = Printer(fmt)
    obj_type, kwargs = parse_filters(obj_type, title, dynamic, escape, allow_inst)
    objects = plex.find_objects(obj_type, **kwargs)  # type: Iterable[Track]
    if objects:
        if full_info:
            p.pprint({repr(obj): obj.as_dict() for obj in objects})
            # for obj in objects:
            #     print(f'{obj.artist().title}\t{obj.album().title}\t{obj.title}\t{obj.userRating}')
        else:
            print(bullet_list(objects))
    else:
        log.warning('No results.')


def sync_playlists(plex):
    from music.plex.playlist import PlexPlaylist

    kpop_tracks = plex.query('track')
    PlexPlaylist('K-Pop Female Solo Artists 3+ Stars', plex).sync_or_create(query=kpop_tracks.filter(
        userRating__gte=6, grandparentTitle__like='taeyeon|chungha|younha|heize|rothy|sunmi|ailee'
    ))
    PlexPlaylist('K-Pop ALL', plex).sync_or_create(query=kpop_tracks)
    PlexPlaylist('K-Pop 1 Star', plex).sync_or_create(query=kpop_tracks.filter(userRating=2))
    PlexPlaylist('K-Pop 2 Stars', plex).sync_or_create(query=kpop_tracks.filter(userRating=4))
    PlexPlaylist('K-Pop 3 Stars', plex).sync_or_create(query=kpop_tracks.filter(userRating=6))
    PlexPlaylist('K-Pop 3+ Stars', plex).sync_or_create(query=kpop_tracks.filter(userRating__gte=6))
    PlexPlaylist('K-Pop 3\u00BD Stars', plex).sync_or_create(query=kpop_tracks.filter(userRating=7))
    PlexPlaylist('K-Pop 3\u00BD+ Stars', plex).sync_or_create(query=kpop_tracks.filter(userRating__gte=7))
    PlexPlaylist('K-Pop 4 Stars', plex).sync_or_create(query=kpop_tracks.filter(userRating=8))
    PlexPlaylist('K-Pop 4+ Stars', plex).sync_or_create(query=kpop_tracks.filter(userRating__gte=8))
    PlexPlaylist('K-Pop 4~4\u00BD Stars', plex).sync_or_create(
        query=kpop_tracks.filter(userRating__gte=8, userRating__lte=9)
    )
    PlexPlaylist('K-Pop 4\u00BD Stars', plex).sync_or_create(query=kpop_tracks.filter(userRating=9))
    PlexPlaylist('K-Pop 5 Stars', plex).sync_or_create(query=kpop_tracks.filter(userRating__gte=10))
    PlexPlaylist('K-Pop Unrated', plex).sync_or_create(
        query=kpop_tracks.filter(
            userRating=0,
            genre__like_exact='k-?pop',
            genre__not_like='christmas',
            title__not_like=r'(?:^|\()(?:intro|outro)(?:$|\s|:|\))|\(inst(?:\.?|rumental)|(?:japanese|jp|karaoke|mandarin|chinese) ver(?:\.|sion)|christmas|santa|remix|snow',
            parentTitle__not_like='christmas|santa',
            duration__gte=60000,
        ).unique()
    )
    PlexPlaylist('K-Pop Unrated from Known Artists', plex).sync_or_create(
        query=kpop_tracks.filter(userRating__gte=6).artists().tracks().filter(
            userRating=0,
            genre__like_exact='k-?pop',
            genre__not_like='christmas',
            title__not_like=r'(?:^|\()(?:intro|outro)(?:$|\s|:|\))|\(inst(?:\.?|rumental)|(?:japanese|jp|karaoke|mandarin|chinese) ver(?:\.|sion)|christmas|santa|remix|snow',
            parentTitle__not_like='christmas|santa',
            duration__gte=60000,
        ).unique()
    )
