import logging
from functools import cached_property

from cli_command_parser import Command, SubCommand, Counter, Positional, Option, Flag, PassThru, ParamGroup

from ..__version__ import __author_email__, __version__  # noqa
from ds_tools.output.constants import PRINTER_FORMATS

log = logging.getLogger(__name__)
OBJ_TYPES = ('track', 'artist', 'album', 'tracks', 'artists', 'albums')
OPS = (
    'contains, endswith, exact, exists, gt, gte, icontains, iendswith, iexact, in, iregex, istartswith, like, lt, '
    'lte, ne, regex, startswith'
)
DESCRIPTION = """Plex Manager

You will be securely prompted for your password for the first login, after which a session token will be cached
"""


class PlexManager(Command, description=DESCRIPTION):
    sub_cmd = SubCommand()
    with ParamGroup('Common') as group:
        verbose = Counter('-v', help='Increase logging verbosity (can specify multiple times)')
        dry_run = Flag('-D', help='Print the actions that would be taken instead of taking them')
        server_path_root = Option('-r', metavar='PATH', help='The root of the path to use from this computer to generate paths to files from the path used by Plex.  When you click on the "..." for a song in Plex and click "Get Info", there will be a path in the "Files" box - for example, "/media/Music/a_song.mp3".  If you were to access that file from this computer, and the path to that same file is "//my_nas/media/Music/a_song.mp3", then the server_path_root would be "//my_nas/" (only needed when not already cached)')
        server_url = Option('-u', metavar='URL', help='The proto://host:port to use to connect to your local Plex server - for example: "https://10.0.0.100:12000" (only needed when not already cached)')
        username = Option('-n', help='Plex username (only needed when a token is not already cached)')
        config_path = Option('-c', metavar='PATH', default='~/.config/plexapi/config.ini', help='Config file in which your token and server_path_root / server_url are stored')
        music_library = Option('-m', default=None, help='Name of the Music library to use (default: Music)')

    def __init__(self):
        from ds_tools.logging import init_logging
        init_logging(self.verbose, log_path=None, names=None, millis=True)

        from music.files.patches import apply_mutagen_patches
        apply_mutagen_patches()

    @cached_property
    def plex(self):
        from music.plex import LocalPlexServer

        return LocalPlexServer(
            self.server_url, self.username, self.server_path_root, self.config_path, self.music_library, self.dry_run
        )


@PlexManager.sub_cmd.register('sync ratings', help='Sync song rating information between Plex and files')
class SyncRatings(PlexManager):
    direction = Positional(choices=('to_files', 'from_files'), help='Direction to sync information')
    path_filter = Option('-f', help='If specified, paths that will be synced must contain the given text (not case sensitive)')

    def main(self, *args, **kwargs):
        from music.plex.ratings import sync_ratings
        sync_ratings(self.plex, self.direction, self.path_filter)


@PlexManager.sub_cmd.register('sync playlists', help='Sync playlists with custom filters')
class SyncPlaylists(PlexManager):
    def main(self, *args, **kwargs):
        from music.plex.playlist import PlexPlaylist

        kpop_tracks = self.plex.query('track', mood__ne='Duplicate Rating')
        PlexPlaylist('K-Pop Female Solo Artists 3+ Stars', self.plex).sync_or_create(
            query=kpop_tracks.filter(
                userRating__gte=6, grandparentTitle__like='taeyeon|chungha|younha|heize|rothy|sunmi|ailee'
            )
        )
        PlexPlaylist('K-Pop ALL', self.plex).sync_or_create(query=kpop_tracks)
        PlexPlaylist('K-Pop 1 Star', self.plex).sync_or_create(query=kpop_tracks.filter(userRating=2))
        PlexPlaylist('K-Pop 2 Stars', self.plex).sync_or_create(query=kpop_tracks.filter(userRating=4))
        PlexPlaylist('K-Pop 3 Stars', self.plex).sync_or_create(query=kpop_tracks.filter(userRating=6))
        PlexPlaylist('K-Pop 3+ Stars', self.plex).sync_or_create(query=kpop_tracks.filter(userRating__gte=6))
        PlexPlaylist('K-Pop 3\u00BD Stars', self.plex).sync_or_create(query=kpop_tracks.filter(userRating=7))
        PlexPlaylist('K-Pop 3\u00BD+ Stars', self.plex).sync_or_create(query=kpop_tracks.filter(userRating__gte=7))
        PlexPlaylist('K-Pop 4 Stars', self.plex).sync_or_create(query=kpop_tracks.filter(userRating=8))
        PlexPlaylist('K-Pop 4+ Stars', self.plex).sync_or_create(query=kpop_tracks.filter(userRating__gte=8))
        PlexPlaylist('K-Pop 4~4\u00BD Stars', self.plex).sync_or_create(
            query=kpop_tracks.filter(userRating__gte=8, userRating__lte=9)
        )
        PlexPlaylist('K-Pop 4\u00BD Stars', self.plex).sync_or_create(query=kpop_tracks.filter(userRating=9))
        PlexPlaylist('K-Pop 5 Stars', self.plex).sync_or_create(query=kpop_tracks.filter(userRating__gte=10))
        PlexPlaylist('K-Pop Unrated', self.plex).sync_or_create(
            query=kpop_tracks.filter(
                userRating=0,
                genre__like_exact='k-?pop',
                genre__not_like='christmas',
                title__not_like=r'(?:^|\()(?:intro|outro)(?:$|\s|:|\))|\(inst(?:\.?|rumental)|(?:japanese|jp|karaoke|mandarin|chinese) ver(?:\.|sion)|christmas|santa|remix|snow',
                parentTitle__not_like='christmas|santa',
                duration__gte=60000,
            ).unique()
        )
        PlexPlaylist('K-Pop Unrated from Known Artists', self.plex).sync_or_create(
            query=kpop_tracks.filter(userRating__gte=6).artists().tracks().filter(
                userRating=0,
                genre__like_exact='k-?pop',
                genre__not_like='christmas',
                title__not_like=r'(?:^|\()(?:intro|outro)(?:$|\s|:|\))|\(inst(?:\.?|rumental)|(?:japanese|jp|karaoke|mandarin|chinese) ver(?:\.|sion)|christmas|santa|remix|snow',
                parentTitle__not_like='christmas|santa',
                duration__gte=60000,
            ).unique()
        )


class Find(PlexManager, help='Find Plex information'):
    obj_type = Positional(choices=OBJ_TYPES, help='Object type')
    title = Positional(nargs='*', help='Object title (optional)')
    escape = Option('-e', default='()', help='Escape the provided regex special characters')
    allow_inst = Flag('-I', help='Allow search results that include instrumental versions of songs')
    full_info = Flag('-F', help='Print all available info about the discovered objects')
    format = Option('-f', choices=PRINTER_FORMATS, default='yaml', help='Output format to use for --full_info')
    query = PassThru(help=f'Query in the format <field><operation><value>; valid operations: {OPS}')

    def main(self, *args, **kwargs):
        from typing import Iterable

        from plexapi.audio import Track

        from ds_tools.output import bullet_list, Printer
        from music.plex.query_parsing import PlexQuery

        p = Printer(self.format)
        filters = PlexQuery.parse(
            ' '.join(self.query) if self.query else None,
            self.escape,
            self.allow_inst,
            title=' '.join(self.title),
        )
        objects = self.plex.find_objects(self.obj_type, **filters)  # type: Iterable[Track]

        if objects:
            if self.full_info:
                p.pprint({repr(obj): obj.as_dict() for obj in objects})
                # for obj in objects:
                #     print(f'{obj.artist().title}\t{obj.album().title}\t{obj.title}\t{obj.userRating}')
            else:
                print(bullet_list(objects))
        else:
            log.warning('No results.')


class Rate(PlexManager, help='Update ratings in Plex'):
    obj_type = Positional(choices=OBJ_TYPES, help='Object type')
    rating: int = Positional(help='Rating out of 10')
    title = Positional(nargs='*', help='Object title (optional)')
    escape = Option('-e', default='()', help='Escape the provided regex special characters (default: %(default)r)')
    allow_inst = Flag('-I', help='Allow search results that include instrumental versions of songs')
    query = PassThru(help=f'Query in the format <field><operation><value>; valid operations: {OPS}')

    def main(self, *args, **kwargs):
        from music.plex.ratings import find_and_rate
        from music.plex.query_parsing import PlexQuery

        filters = PlexQuery.parse(
            ' '.join(self.query) if self.query else None,
            self.escape,
            self.allow_inst,
            title=' '.join(self.title),
        )
        find_and_rate(
            self.plex, self.rating, self.obj_type, self.title, filters, self.escape, self.allow_inst, pre_parsed=True
        )


class RateOffset(PlexManager, help='Update all track ratings in Plex with an offset'):
    min_rating: int = Option('-min', default=2, help='Minimum rating for which a change will be made')
    max_rating: int = Option('-max', default=10, help='Maximum rating for which a change will be made')
    offset: int = Option('-o', default=-1, help='Adjustment to make')

    def main(self, *args, **kwargs):
        from music.plex.ratings import adjust_track_ratings

        adjust_track_ratings(self.plex, self.min_rating, self.max_rating, self.offset)


class Playlist(PlexManager, help='Save or compare playlists'):
    sub_cmd = SubCommand()


class Dump(Playlist, help='Save playlists'):
    path = Positional(help='Playlist dump location')
    playlist = Option('-p', help='Dump the specified playlist (default: all)')

    def main(self, *args, **kwargs):
        from music.plex.playlist import dump_playlists

        dump_playlists(self.plex, self.path, self.playlist)


class Compare(Playlist, help='Compare playlists'):
    path = Positional(help='Playlist dump location')
    playlist = Option('-p', help='Compare the specified playlist (default: all)')
    strict = Flag('-s', help='Perform a strict comparison (default: by artist/album/title)')

    def main(self, *args, **kwargs):
        from music.plex.playlist import compare_playlists

        compare_playlists(self.plex, self.path, self.playlist, self.strict)


class List(Playlist, help='List playlists in a dump'):
    path = Positional(help='Playlist dump location')

    def main(self, *args, **kwargs):
        from music.plex.playlist import list_playlists

        list_playlists(self.plex, self.path)


class ShowDupeRatings(PlexManager, help='Show duplicate ratings'):
    def main(self, *args, **kwargs):
        from music.plex.ratings import print_dupe_ratings_by_artist

        print_dupe_ratings_by_artist(self.plex)


class FixBlankTitles(PlexManager, help='Fix albums containing tracks with blank titles'):
    def main(self, *args, **kwargs):
        albums = {track.album() for track in self.plex.get_tracks() if track.title == ''}
        log.info(f'Found {len(albums)} albums containing tracks that have blank titles')
        for album in sorted(albums):
            log.info(f'  - Refreshing: {album}')
            album.refresh()
