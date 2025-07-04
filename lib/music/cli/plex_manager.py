from __future__ import annotations

import logging
from functools import cached_property, partial
from pathlib import Path
from typing import TYPE_CHECKING, Iterator

from cli_command_parser import Command, Counter, Positional, Option, Flag, PassThru, ParamGroup, main  # noqa
from cli_command_parser import SubCommand, Action
from cli_command_parser.inputs import Path as IPath, Date, TimeDelta
from ds_tools.output.constants import PRINTER_FORMATS

if TYPE_CHECKING:
    from plexapi.video import Movie
    from ds_tools.output.prefix import LoggingPrefix
    from music.plex import LocalPlexServer
    from music.plex.playlist import PlexPlaylist

log = logging.getLogger(__name__)
OBJ_TYPES = ('track', 'artist', 'album', 'tracks', 'artists', 'albums')
QUERY_OPS = (
    'contains, endswith, exact, exists, gt, gte, icontains, iendswith, iexact, in, iregex, istartswith, like, lt, '
    'lte, ne, regex, startswith'
)
_PATH_ROOT_HELP = """
The root of the path to use from this computer to generate paths to files from the path used by Plex.
When you click on the "..." for a song in Plex and click "Get Info", there will be a path in the "Files" box -
for example, "/media/Music/a_song.mp3".  If you were to access that file from this computer, and the path to that
same file is "//my_nas/media/Music/a_song.mp3", then the server_path_root would be "//my_nas/" (only needed when not
already cached)
"""
_URL_HELP = (
    'The proto://host:port to use to connect to your local Plex server -'
    ' for example: "https://10.0.0.100:12000" (only needed when not already cached)'
)


class PlexManager(Command):
    """
    Plex Manager

    You will be securely prompted for your password for the first login, after which a session token will be cached
    """

    sub_cmd = SubCommand()
    with ParamGroup('Server / Connection'):
        server_path_root = Option(metavar='PATH', help=_PATH_ROOT_HELP)
        server_url = Option(metavar='URL', help=_URL_HELP)
        username = Option(help='Plex username (only needed when a token is not already cached)')
        config_path = Option(
            metavar='PATH', default='~/.config/plexapi/config.ini',
            help='Config file in which your token and server_path_root / server_url are stored'
        )

    with ParamGroup('Library'):
        music_library = Option('-m', default=None, help='Name of the Music library to use (default: Music)')
        movie_library = Option(default=None, help='Name of the Movies library to use')
        tv_library = Option(default=None, help='Name of the TV library to use')

    with ParamGroup('Common'):
        verbose = Counter('-v', help='Increase logging verbosity (can specify multiple times)')
        dry_run = Flag('-D', help='Print the actions that would be taken instead of taking them')

    _use_log_file: bool = False

    def __init_subclass__(cls, use_log_file: bool = False, **kwargs):
        super().__init_subclass__(**kwargs)
        if use_log_file:
            cls._use_log_file = use_log_file

    def _init_command_(self):
        from ds_tools.logging import init_logging

        kwargs = {} if self._use_log_file else {'log_path': None}
        init_logging(self.verbose, names=None, millis=True, set_levels={'paramiko.transport': 50}, **kwargs)

        from music.files.patches import apply_mutagen_patches

        apply_mutagen_patches()

    @cached_property
    def lp(self) -> LoggingPrefix:
        from ds_tools.output.prefix import LoggingPrefix

        return LoggingPrefix(self.dry_run)

    @cached_property
    def plex(self) -> LocalPlexServer:
        from music.plex import LocalPlexServer

        return LocalPlexServer(
            url=self.server_url,
            user=self.username,
            server_path_root=self.server_path_root,
            config_path=self.config_path,
            music_library=self.music_library,
            movie_library=self.movie_library,
            tv_library=self.tv_library,
            dry_run=self.dry_run,
        )


# region Sync Commands


class SyncRatings(PlexManager, choice='sync ratings', help='Sync song rating information between Plex and files'):
    direction = Positional(choices=('to_files', 'from_files'), help='Direction to sync information')
    path_filter = Option('-f', help='Only sync tracks with paths that contain the given text (not case sensitive)')
    parallel: int = Option('-P', default=4, help='Number of workers to use in parallel')

    with ParamGroup(mutually_exclusive=True):
        before = Option('-b', type=Date(), help='Only sync files last modified before this date')
        before_days = Option('-B', type=TimeDelta('days'), help='Only sync files last modified before this many days ago')
    with ParamGroup(mutually_exclusive=True):
        after = Option('-a', type=Date(), help='Only sync files last modified after this date')
        after_days = Option('-A', type=TimeDelta('days'), help='Only sync files last modified after this many days ago')

    def main(self):
        from music.plex.ratings import RatingSynchronizer

        before = self.before_days or self.before
        after = self.after_days or self.after
        rs = RatingSynchronizer(self.plex, self.path_filter, self.parallel, mod_before=before, mod_after=after)
        rs.sync(self.direction == 'from_files')


class SyncPlaylists(PlexManager, choice='sync playlists', help='Sync playlists with custom filters'):
    def main(self):
        from music.plex.playlist import PlexPlaylist

        kpop_tracks = self.plex.query('track', mood__ne='Duplicate Rating')
        playlist = partial(PlexPlaylist, plex=self.plex, externally_synced=True)

        playlist('K-Pop Female Solo Artists 3+ Stars').sync_or_create(
            query=kpop_tracks.filter(
                userRating__gte=6,
                grandparentTitle__like=r'taeyeon|chungha|younha|heize|rothy|sunmi|ailee|lee hi|jo yuri|seori|\biu\b|choi ye.?na|yuju|baek ji young|gummy|yuqi|hong jin young|bibi|hyori|hyolyn|yourbeagle|wendy|whee in|hwa sa|minnie|joy|seulgi|siyeon',
            )
        )
        playlist('K-Pop ALL').sync_or_create(query=kpop_tracks)
        playlist('K-Pop 1 Star').sync_or_create(query=kpop_tracks.filter(userRating=2))
        # playlist('K-Pop 1\u00BD Star').sync_or_create(query=kpop_tracks.filter(userRating=3))
        playlist('K-Pop 2 Stars').sync_or_create(query=kpop_tracks.filter(userRating=4))
        # playlist('K-Pop 2\u00BD Stars').sync_or_create(query=kpop_tracks.filter(userRating=5))
        playlist('K-Pop 3 Stars').sync_or_create(query=kpop_tracks.filter(userRating=6))
        playlist('K-Pop 3+ Stars').sync_or_create(query=kpop_tracks.filter(userRating__gte=6))
        playlist('K-Pop 3\u00BD Stars').sync_or_create(query=kpop_tracks.filter(userRating=7))
        playlist('K-Pop 3\u00BD+ Stars').sync_or_create(query=kpop_tracks.filter(userRating__gte=7))
        playlist('K-Pop 4 Stars').sync_or_create(query=kpop_tracks.filter(userRating=8))
        playlist('K-Pop 4+ Stars').sync_or_create(query=kpop_tracks.filter(userRating__gte=8))
        playlist('K-Pop 4~4\u00BD Stars').sync_or_create(
            query=kpop_tracks.filter(userRating__gte=8, userRating__lte=9)
        )
        playlist('K-Pop 4\u00BD Stars').sync_or_create(query=kpop_tracks.filter(userRating=9))
        playlist('K-Pop 5 Stars').sync_or_create(query=kpop_tracks.filter(userRating__gte=10))
        playlist('K-Pop Unrated').sync_or_create(
            query=kpop_tracks.filter(
                userRating=0,
                genre__like_exact='k-?pop',
                genre__not_like='christmas',
                title__not_like=r'(?:^|\()(?:intro|outro)(?:$|\s|:|\))|\(inst(?:\.?|rumental)|(?:japanese|jp|karaoke|mandarin|chinese) ver(?:\.|sion)|christmas|santa|remix|snow',
                parentTitle__not_like='christmas|santa',
                duration__gte=60000,
            ).unique()
        )
        playlist('K-Pop Unrated from Known Artists').sync_or_create(
            query=kpop_tracks.filter(userRating__gte=6).artists().tracks().filter(
                userRating=0,
                genre__like_exact='k-?pop',
                genre__not_like='christmas',
                title__not_like=r'(?:^|\()(?:intro|outro)(?:$|\s|:|\))|\(inst(?:\.?|rumental)|(?:japanese|jp|karaoke|mandarin|chinese) ver(?:\.|sion)|christmas|santa|remix|snow',
                parentTitle__not_like='christmas|santa',
                duration__gte=60000,
            ).unique()
        )


# endregion


class Find(PlexManager, help='Find Plex information'):
    obj_type = Positional(choices=OBJ_TYPES, help='Object type')
    title = Positional(nargs='*', help='Object title (optional)')
    escape = Option('-e', default='()', help='Escape the provided regex special characters')
    allow_inst = Flag('-I', help='Allow search results that include instrumental versions of songs')
    full_info = Flag('-F', help='Print all available info about the discovered objects')
    format = Option('-f', choices=PRINTER_FORMATS, default='yaml', help='Output format to use for --full_info')
    query = PassThru(help=f'Query in the format <field><operation><value>; valid operations: {QUERY_OPS}')

    def main(self):
        from ds_tools.output import bullet_list, Printer
        from music.plex.query_parsing import PlexQuery

        p = Printer(self.format)
        filters = PlexQuery.parse(
            ' '.join(self.query) if self.query else '',
            escape=self.escape,
            allow_inst=self.allow_inst,
            title=' '.join(self.title),
        )
        if objects := self.plex.find_objects(self.obj_type, **filters):
            if self.full_info:
                p.pprint({repr(obj): obj.as_dict() for obj in objects})
                # for obj in objects:
                #     print(f'{obj.artist().title}\t{obj.album().title}\t{obj.title}\t{obj.userRating}')
            else:
                print(bullet_list(objects))
        else:
            log.warning('No results.')


# region Rating Commands


class Rate(PlexManager, help='Update ratings in Plex'):
    obj_type = Positional(choices=OBJ_TYPES, help='Object type')
    rating: int = Positional(help='Rating out of 10')
    title = Positional(nargs='*', help='Object title (optional)')
    escape = Option('-e', default='()', help='Escape the provided regex special characters (default: %(default)r)')
    allow_inst = Flag('-I', help='Allow search results that include instrumental versions of songs')
    query = PassThru(help=f'Query in the format <field><operation><value>; valid operations: {QUERY_OPS}')

    def main(self):
        from music.plex.ratings import find_and_rate
        from music.plex.query_parsing import PlexQuery

        filters = PlexQuery.parse(
            ' '.join(self.query) if self.query else '',
            escape=self.escape,
            allow_inst=self.allow_inst,
            title=' '.join(self.title),
        )
        find_and_rate(
            self.plex, self.rating, self.obj_type, self.title, filters, self.escape, self.allow_inst, pre_parsed=True
        )


class RateOffset(PlexManager, help='Update all track ratings in Plex with an offset'):
    min_rating: int = Option('-min', default=2, help='Minimum rating for which a change will be made')
    max_rating: int = Option('-max', default=10, help='Maximum rating for which a change will be made')
    offset: int = Option('-o', default=-1, help='Adjustment to make')

    def main(self):
        from music.plex.ratings import adjust_track_ratings

        adjust_track_ratings(self.plex, self.min_rating, self.max_rating, self.offset)


# endregion


# region Playlist Commands


class Playlist(PlexManager, help='Save or compare playlists'):
    sub_cmd = SubCommand()


class Dump(Playlist, help='Save playlists', use_log_file=True):
    path = Positional(help='Playlist dump location')
    compress = Flag('--no-compress', '-C', default=True, help='Do NOT compress the playlist dump')
    format = Option('-f', choices=('json', 'xml'), default='json', help='Serialization format')
    with ParamGroup(mutually_exclusive=True):
        playlist = Option('-p', help='Dump the specified playlist (default: all)')
        separate = Flag('-s', help='Store each playlist in a separate file (default: combine)')

    def main(self):
        if self.playlist:
            self.plex.playlist(self.playlist).dump(self.path, self.compress)
        else:
            from music.plex.playlist import PlaylistSerializer

            serializer = PlaylistSerializer(self.path, self.plex, compress=self.compress, xml=self.format == 'xml')
            serializer.dump_all(self.separate)


class Compare(Playlist, help='Compare playlists'):
    path = Positional(help='Playlist dump location')
    playlist = Option('-p', help='Compare the specified playlist (default: all)')
    strict = Flag('-s', help='Perform a strict comparison (default: by artist/album/title)')

    def main(self, *args, **kwargs):
        from music.plex.playlist import compare_playlists

        compare_playlists(self.plex, self.path, self.playlist, self.strict)


class Show(Playlist, help='Show a playlist and its contents'):
    name = Positional(help='The name of the playlist to show')
    path = Option('-p', help='Load the playlist from the specified dump location instead of the live server')
    hide_tracks = Flag('-H', help='Hide tracks and only print metadata')

    def main(self):
        self._get_playlist().pprint(show_tracks=not self.hide_tracks)

    def _get_playlist(self) -> PlexPlaylist:
        if self.path:
            from music.plex.playlist import PlexPlaylist

            return PlexPlaylist.load_all(self.path, self.plex)[self.name]
        else:
            return self.plex.playlist(self.name)


class List(Playlist, help='List playlists'):
    path = Option('-p', help='List playlists from the specified dump location instead of the live server')

    with ParamGroup(mutually_exclusive=True):
        show_tracks = Flag('-t', help='Show all tracks in each playlist (may be very verbose)')
        names_only = Flag('-N', help='Show playlist names only (default: show some metadata)')

    with ParamGroup('Filter'):
        name = Option('-n', metavar='GLOB', help='Filter playlists to include only ones matching the provided pattern')
        ordered = Flag('-o', help='Only include ordered playlists (exclude "smart" and externally synced ones)')
        max_size: int = Option('-s', help='Exclude playlists with more items than the specified size')

    def main(self):
        for name, playlist in self.get_playlists().items():
            if self.names_only:
                print(name)
            else:
                playlist.pprint(show_tracks=self.show_tracks)

    def get_playlists(self) -> dict[str, PlexPlaylist]:
        playlists = self._get_playlists()
        if self.name:
            from fnmatch import fnmatch

            playlists = {name: playlist for name, playlist in playlists.items() if fnmatch(name, self.name)}

        if self.ordered:
            playlists = {name: playlist for name, playlist in playlists.items() if playlist.is_ordered}

        if self.max_size and self.max_size > 0:
            playlists = {name: playlist for name, playlist in playlists.items() if len(playlist) <= self.max_size}

        return playlists

    def _get_playlists(self) -> dict[str, PlexPlaylist]:
        if self.path:
            from music.plex.playlist import PlexPlaylist

            playlists = PlexPlaylist.load_all(self.path, self.plex)
            return {name: pl for name, pl in sorted(playlists.items())}
        else:
            return self.plex.playlists  # pre-sorted


# endregion


# region Reports

class Report(PlexManager, help='Show A report'):
    sub_cmd = SubCommand(help='The report to show')


class ShowDupeRatings(Report, choice='dupe ratings', help='Show duplicate ratings'):
    def main(self):
        from music.plex.ratings import print_dupe_ratings_by_artist

        print_dupe_ratings_by_artist(self.plex)


class ShowMissingAnalysis(
    Report, choice='missing analysis', help='Report showing albums that are missing loudness analysis'
):
    format = Option('-f', choices=PRINTER_FORMATS, default='yaml', help='Output format')
    max_age: int = Option('-A', default=180, help='Max age (in seconds) for the local DB cache before refreshing it')

    def main(self):
        from ds_tools.output.printer import Printer
        from ds_tools.output.table import Table, SimpleColumn as Col
        from music.plex.db import PlexDB

        db = PlexDB.from_remote_server(max_age=self.max_age)
        if self.format == 'table':
            columns = ('lib_section', 'artist_id', 'artist', 'album_id', 'album', 'track_num', 'track', 'track_id')
            table = Table(*(Col(c) for c in columns), sort_by=columns[:3], sort=True, update_width=True)
            table.print_rows(db.find_missing_analysis_table())
        else:
            Printer(self.format).pprint(db.find_missing_analysis_name_map())


# endregion


class FixBlankTitles(PlexManager, choice='fix blank titles', help='Fix albums containing tracks with blank titles'):
    def main(self):
        albums = {track.album() for track in self.plex.get_tracks() if track.title == ''}
        log.info(f'Found {len(albums)} albums containing tracks that have blank titles')
        for album in sorted(albums):
            log.info(f'  - Refreshing: {album}')
            album.refresh()


class SyncPlayed(PlexManager, choice='sync played', help='Sync played status for movies'):
    action = Action(help='Whether data should be loaded or dumped')
    data_path: Path = Option(
        '-p', type=IPath(type='file'), help='Path in which data should be stored/loaded', required=True
    )
    only_played = Flag('-o', help='On load: only sync movies where played should become True.  On dump: ignored.')

    @action
    def load(self):
        """Load and set played status for movies based on the given file"""
        if not self.data_path.exists():
            raise ValueError(f'Invalid path - it does not exist: {self.data_path}')
        elif not self.data_path.is_file():
            raise ValueError(f'Invalid path - it is not a file: {self.data_path}')

        import json

        with self.data_path.open('r') as f:
            data = json.load(f)

        if self.only_played:
            data = {k: v for k, v in data.items() if v}

        to_update = {}
        for movie, path, is_played in self.iter_movies():
            if (was_played := data.get(path.name)) is not None and was_played != is_played:
                to_update[movie] = was_played

        for movie, played in sorted(to_update.items(), key=lambda kv: kv[0].title):
            log.info(f'{self.lp.update} key={movie._int_key} year={movie.year} title={movie.title!r} {played=}')
            if not self.dry_run:
                if played:
                    movie.markPlayed()
                else:
                    movie.markUnplayed()

    @action
    def dump(self):
        """Dump played status of all movies to the specified file"""
        if self.data_path.exists():
            raise ValueError(f'Invalid path - it must not exist: {self.data_path}')
        self.data_path.parent.mkdir(parents=True, exist_ok=True)

        import json

        data = {path.name: is_played for movie, path, is_played in self.iter_movies()}
        log.info(f'{self.lp.save} played data for {len(data)} movies to {self.data_path.as_posix()}')
        if not self.dry_run:
            with self.data_path.open('w') as f:
                json.dump(data, f, indent=4, sort_keys=True)

    def iter_movies(self) -> Iterator[tuple[Movie, Path, bool]]:
        for movie in self.plex.find_objects('movie'):
            is_played = movie.isPlayed
            for media in movie.media:  # noqa
                for part in media.parts:
                    yield movie, Path(part.file), is_played
