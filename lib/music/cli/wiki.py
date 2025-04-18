from __future__ import annotations

from cli_command_parser import Command, SubCommand, Counter, Positional, Option, Flag, ParamGroup, main  # noqa
from cli_command_parser.inputs import NumRange

from music.wiki import EntertainmentEntity

ALL_SITES = ('kpop.fandom.com', 'www.generasia.com', 'wiki.d-addicts.com', 'en.wikipedia.org')


class Wiki(Command, description='Wiki matching / informational functions'):
    sub_cmd = SubCommand()
    with ParamGroup('Common') as group:
        verbose = Counter('-v', help='Increase logging verbosity (can specify multiple times)')
        dry_run = Flag('-D', help='Print the actions that would be taken instead of taking them')
        match_log = Flag(help='Enable debug logging for the album match processing logger')

    def _init_command_(self):
        import logging
        from ds_tools.logging import init_logging

        init_logging(self.verbose, log_path=None, names=None)

        from music.files.patches import apply_mutagen_patches
        apply_mutagen_patches()

        # logging.getLogger('wiki_nodes.http.query').setLevel(logging.DEBUG)
        if self.match_log:
            logging.getLogger('music.manager.wiki_match.matching').setLevel(logging.DEBUG)


class Pprint(Wiki, help='Pretty-print the parsed Wiki content for a given URL'):
    url = Positional(help='A wiki entity URL')
    mode = Option(
        '-m', choices=('content', 'processed', 'reprs', 'headers', 'raw'), default='content', help='Pprint mode'
    )
    infobox = Flag('-i', help='Print only the infobox (default: all sections)')

    def main(self):
        from music.manager.wiki_info import pprint_wiki_page

        pprint_wiki_page(self.url, self.mode, self.infobox)


class Raw(Wiki, help='Show the raw Wiki text content for a given URL'):
    url = Positional(help='A wiki entity URL')

    def main(self):
        from music.manager.wiki_info import pprint_wiki_page

        pprint_wiki_page(self.url, 'raw')


class Show(Wiki, help='Show a parsed wiki entity'):
    identifier = Positional(help='A wiki URL or title/name')
    expand = Counter('-x', help='Expand entities with a lot of nested info (may be specified multiple times to increase expansion level)')
    limit: int = Option('-L', default=0, help='Maximum number of discography entry parts to show for a given album (default: unlimited)')
    types = Option('-t', nargs='+', help='Filter albums to only those that match the specified types')
    type = Option('-T', choices=[c.__name__ for c in EntertainmentEntity._subclasses], help='An EntertainmentEntity subclass to require that the given page matches')
    site = Option('-s', choices=ALL_SITES, help='The site from which the entity originated, if a path is provided as the identifier')

    def main(self):
        from music.manager.wiki_info import show_wiki_entity

        show_wiki_entity(self.identifier, self.expand, self.limit, self.types, self.type, self.site)


class Update(Wiki, help='Update one or more albums based on info from a Wiki'):
    path = Positional(nargs='+', help='One or more paths of music files or directories containing music files')
    destination = Option('-d', metavar='PATH', help=f"Destination base directory for sorted files (default: based on today's date)")
    url = Option('-u', help='A wiki URL (can only specify one file/directory when providing a URL)')
    collab_mode = Option('-c', choices=('title', 'artist', 'both'), default='artist', help='List collaborators in the artist tag, the title tag, or both')
    artist = Option('-a', metavar='URL', help='Force the use of the given artist instead of an automatically discovered one')
    soloist = Flag('-S', help='For solo artists, use only their name instead of including their group, and do not sort them with their group')
    hide_edition = Flag('-E', help='Exclude the edition from the album title, if present (default: include it)')
    title_case = Flag('-T', help='Fix track and album names to use Title Case when they are all caps')
    update_cover = Flag('-C', help='Update the cover art for the album if it does not match an image in the matched wiki page')
    no_album_move = Flag('-M', help='Do not rename the album directory')
    artist_only = Flag('-I', help='Only match the artist / only use the artist URL if provided')
    replace_genre = Flag('-G', help='Replace genre instead of combining genres')

    with ParamGroup('Site', mutually_exclusive=True):
        sites = Option('-s', nargs='+', choices=ALL_SITES, help='The wiki sites to search')
        all = Flag('-A', help='Search all sites')
        ost = Flag('-O', help='Search only wiki.d-addicts.com')
    with ParamGroup('BPM', mutually_exclusive=True):
        bpm = Flag('-b', help='Add a BPM tag if it is not already present (default: True if aubio is installed)')
        no_bpm = Flag('-B', default=True, help='Do not add a BPM tag if it is not already present')
    with ParamGroup('Track Data', mutually_exclusive=True):
        dump = Option('-P', metavar='PATH', help='Dump track updates to a json file instead of updating the tracks')
        load = Option('-L', metavar='PATH', help='Load track updates from a json file instead of from a wiki')

    def main(self):
        from datetime import date
        from music.manager.config import UpdateConfig
        from music.manager.wiki_update import WikiUpdater
        from music.common.utils import can_add_bpm

        sites = self.sites or (['wiki.d-addicts.com'] if self.ost else ALL_SITES)
        config = UpdateConfig(
            soloist=self.soloist,
            hide_edition=self.hide_edition,
            collab_mode=self.collab_mode,
            artist_url=self.artist,
            add_bpm=can_add_bpm() if not self.bpm and self.no_bpm else self.bpm,
            title_case=self.title_case,
            artist_sites=sites,
            album_sites=sites,
            update_cover=self.update_cover,
            no_album_move=self.no_album_move,
            artist_only=self.artist_only,
            add_genre=not self.replace_genre,
        )
        WikiUpdater(self.path, config).update(
            self.destination or f'./sorted_{date.today().isoformat()}',
            load_path=self.load,
            album_url=self.url,
            dry_run=self.dry_run,
            dump=self.dump,
        )


class Match(Wiki, help='Attempt to find a Wiki page that matches a given album directory'):
    path = Positional(nargs='+', help='One or more paths of music files or directories containing music files')

    def main(self):
        from music.manager.wiki_match import show_album_dir_matches

        show_album_dir_matches(self.path)


class Find(Wiki, help='Attempt to find a Wiki page that matches the specified criteria'):
    title = Option('-t', required=True, help='The title of the album to find')
    artist = Option('-a', required=True, help='The name of the artist that released the album')
    track_count: int = Option('-c', type=NumRange(min=1), help='The number of tracks in the album')
    sites = Option('-s', nargs='+', choices=ALL_SITES, help='The wiki sites to search')

    def main(self):
        from music.manager.wiki_match import AlbumMetaData, show_matches

        album_meta = AlbumMetaData.parse(
            name=self.title,
            artist=self.artist,
            track_count=self.track_count,
        )
        show_matches(album_meta, sites=self.sites)


class Test(Wiki, help='Test the compatibility of a given album directory with a given Wiki page'):
    path = Positional(help='One path of music files or directories containing music files')
    url = Positional(help='A wiki URL for a page to test whether it matches the given files')

    def main(self):
        from music.manager.wiki_match import test_match

        test_match(self.path, self.url)
