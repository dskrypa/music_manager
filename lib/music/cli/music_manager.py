from __future__ import annotations

from typing import TYPE_CHECKING

from cli_command_parser import Command, SubCommand, Counter, Positional, Option, Flag, ParamGroup, main  # noqa

from music.__version__ import __author_email__, __version__  # noqa

if TYPE_CHECKING:
    from music.files.album import AlbumDir


class MusicManager(Command, description='Music Manager'):
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


# region Show Commands


class Show(MusicManager, help='Show song/tag information'):
    sub_cmd = SubCommand()


class ShowInfo(Show, choice='info', help='Show track title, length, tag version, and tags'):
    path = Positional(nargs='*', help='Paths for music files or directories containing music files')
    tags = Option('-t', nargs='+', help='The tags to display')
    no_trim = Flag('-T', help='Do not trim tag IDs')

    def main(self):
        from music.manager.file_info import print_track_info
        print_track_info(self.path or '.', self.tags, trim=not self.no_trim)


class ShowMeta(Show, choice='meta', help='Show track title, length, and tag version'):
    path = Positional(nargs='*', help='Paths for music files or directories containing music files')

    def main(self):
        from music.manager.file_info import print_track_info
        print_track_info(self.path or '.', meta_only=True)


class ShowCount(Show, choice='count', help='Count tracks by tag'):
    path = Positional(nargs='*', help='Paths for music files or directories containing music files')

    def main(self):
        from music.manager.file_info import table_tag_type_counts
        table_tag_type_counts(self.path or '.')


class ShowTable(Show, choice='table', help='Show tags in a table'):
    path = Positional(nargs='*', help='Paths for music files or directories containing music files')
    tags = Option('-t', nargs='+', help='The tags to display')
    summary = Flag('-s', help='Show a summary of each album instead of the full table')

    def main(self):
        from music.files.album import iter_album_dirs
        from music.manager.file_info import table_song_tags

        if self.summary:
            for n, album_dir in enumerate(iter_album_dirs(self.path or '.')):
                if n:
                    print('\n')

                self.show_album_summary(album_dir)
        else:
            table_song_tags(self.path or '.', self.tags)

    def show_album_summary(self, album_dir: AlbumDir):  # noqa
        from ds_tools.output.color import colored
        from ds_tools.output.table import Table, SimpleColumn

        artist = album_dir.album_artist or album_dir.artist or ', '.join(map(str, sorted(album_dir.all_artists)))
        title = album_dir.title
        print(f'Location: {album_dir.relative_path}')
        print(f'Album: {colored(str(title), 10)}, Artist: {colored(str(artist), 11)}')
        for key, url in {'Artist': album_dir.artist_url, 'Album': album_dir.album_url}.items():
            if url:
                print(f'{key} URL: {url}')

        rows = [{'file': f.path.name, **f.common_tag_info} for f in album_dir]
        try:
            columns = list(rows[0])
        except IndexError:
            print('No tracks found')
            return

        columns.remove('album artist')
        columns.remove('album')
        artists = {f.tag_artist for f in album_dir}
        if len(artists) == 1 and next(iter(artists)) == str(artist):
            columns.remove('artist')

        print()
        tbl = Table(*(SimpleColumn(key) for key in columns), update_width=True)
        tbl.print_rows(rows)


class ShowUnique(Show, choice='unique', help='Count tracks with unique tag values'):
    path = Positional(nargs='*', help='Paths for music files or directories containing music files')
    tags = Option('-t', nargs='+', help='The tags to display', required=True)

    def main(self):
        from music.manager.file_info import table_unique_tag_values
        table_unique_tag_values(self.path or '.', self.tags)


class ShowProcessed(Show, choice='processed', help='Show processed album info'):
    path = Positional(nargs='*', help='Paths for music files or directories containing music files')
    expand = Counter('-x', help='Expand entities with a lot of nested info (may be specified multiple times to increase expansion level)')
    only_errors = Flag('-E', help='Only print entries with processing errors')

    def main(self):
        from music.manager.file_info import print_processed_info
        print_processed_info(self.path or '.', self.expand, self.only_errors)


# endregion


class Path2Tag(MusicManager, choice='path2tag', help='Update tags based on the path to each file'):
    path = Positional(nargs='+', help='One or more paths of music files or directories containing music files')
    title = Flag('-t', help='Update title based on filename')
    yes = Flag('-y', help='Skip confirmation prompts')

    def main(self):
        from music.manager.file_update import path_to_tag
        path_to_tag(self.path, self.dry_run, self.yes, self.title)


class Clean(MusicManager, help='Clean undesirable tags from the specified files'):
    path = Positional(nargs='+', help='One or more paths of music files or directories containing music files')
    with ParamGroup(mutually_exclusive=True):
        bpm = Flag('-b', help='Add a BPM tag if it is not already present (default: True if aubio is installed)')
        no_bpm = Flag('-B', default=True, help='Do not add a BPM tag if it is not already present')

    def main(self):
        from music.manager.file_update import clean_tags
        from music.common.utils import can_add_bpm

        bpm = can_add_bpm() if not self.bpm and self.no_bpm else self.bpm
        clean_tags(self.path, self.dry_run, bpm)


class Remove(MusicManager, help='Remove the specified tags from the specified files'):
    path = Positional(nargs='+', help='One or more paths of music files or directories containing music files')
    with ParamGroup(mutually_exclusive=True, required=True):
        tag = Option('-t', nargs='+', help='Tag ID(s) to remove')
        all = Flag('-A', help='Remove ALL tags')

    def main(self):
        from music.manager.file_update import remove_tags

        remove_tags(self.path, self.tag, self.dry_run, self.all, missing_log_lvl=19 if self.tag else None)


class Bpm(MusicManager, help='Add BPM info to the specified files'):
    path = Positional(nargs='+', help='One or more paths of music files or directories containing music files')
    parallel: int = Option('-P', default=4, help='Maximum number of workers to use in parallel')

    def main(self):
        from music.manager.file_update import add_track_bpm
        add_track_bpm(self.path, self.parallel, self.dry_run)


class ApplyUpdates(MusicManager, choice='apply updates', help='Apply updates from a file'):
    no_album_move = Flag('-M', help='Do not rename the album directory (only applies to --load/-L)')
    replace_genre = Flag('-G', help='Replace genre instead of combining genres')
    load = Option('-L', metavar='PATH', required=True, help='Load updates from a json file (may not be combined with other options)')
    destination = Option('-d', metavar='PATH', help=f"Destination base directory for sorted files (default: based on today's date)")

    def main(self):
        from datetime import date
        from music.manager.update import AlbumInfo

        AlbumInfo.load(self.load).update_and_move(
            dest_base_dir=self.destination or './sorted_{}'.format(date.today().strftime('%Y-%m-%d')),
            dry_run=self.dry_run,
            no_album_move=self.no_album_move,
            add_genre=not self.replace_genre,
        )


class Update(MusicManager, help='Set the value of the given tag on all music files in the given path'):
    path = Positional(nargs='+', help='One or more paths of music files or directories containing music files')
    tag = Option('-t', nargs='+', required=True, help='Tag ID(s) to modify (required)')
    value = Option('-V', required=True, help='Value to replace existing values with (required)')
    replace = Option('-r', nargs='+', help='If specified, only replace tag values that match the given patterns(s)')
    partial = Flag('-p', help='Update only parts of tags that match a pattern specified via --replace/-r')
    regex = Flag('-R', help='Treat the provided --replace / -r values as regex patterns (default: glob)')

    def main(self):
        from music.manager.file_update import update_tags_with_value

        update_tags_with_value(
            self.path, self.tag, self.value, self.replace, self.partial, dry_run=self.dry_run, regex=self.regex
        )


class Dump(MusicManager, help='Dump tag info about the specified files to json'):
    path = Positional(help='A path for a music file or a directory containing music files')
    output = Positional(help='The destination file path')
    title_case = Flag('-T', help='Fix track and album names to use Title Case when they are all caps')

    def main(self):
        from music.manager.update import AlbumInfo

        AlbumInfo.from_path(self.path).dump(self.output, self.title_case)


class Cover(MusicManager, help='Extract or add cover art'):
    path = Positional(help='A path for a music file or a directory containing music files')
    with ParamGroup(mutually_exclusive=True):
        with ParamGroup('Save Cover'):
            save = Option('-s', metavar='PATH', help='Path to save the cover images from the specified file(s)')
        with ParamGroup('Load Cover'):
            load = Option('-L', metavar='PATH', help='Path to an image file')
            max_width: int = Option('-w', default=1200, help='Resize the provided image if it is larger than this value')
        with ParamGroup('Remove Cover'):
            remove = Flag('-R', help='Remove all cover images')

    def main(self):
        from music.manager.images import extract_album_art, set_album_art, del_album_art

        if self.save:
            extract_album_art(self.path, self.save)
        elif self.load:
            set_album_art(self.path, self.load, self.max_width, self.dry_run)
        elif self.remove:
            del_album_art(self.path, self.dry_run)
