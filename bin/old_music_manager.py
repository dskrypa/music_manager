#!/usr/bin/env python
"""
Manage music files


Example usage - List unique tags in the current directory, filtering out known tags::

    $ /c/unix/home/user/git/ds_tools/bin/music_manager.py info . -u '*' | egrep -v 'TIT2|TALB|TCON|TRCK|USLT|APIC|TDRC|TPE1|TPOS|TPE2|nam  \[|wrt  \[|TCOM|trkn|sonm|alb  \[|soa[alr]  \[ |ART  \[|day  \['

Example usage - Remove recommended tags from files in the current directory::

    $ /c/unix/home/user/git/ds_tools/bin/music_manager.py remove . -r

:author: Doug Skrypa
"""

import json
import logging
import os
import pickle
import re
import string
import sys
import traceback
from collections import Counter, defaultdict
from fnmatch import fnmatch, translate as fnpat2re
from pathlib import Path

import mutagen
import mutagen.id3._frames
from mutagen.id3 import ID3, TDRC
from mutagen.mp4 import MP4Tags

from ds_tools.argparsing import ArgParser
from ds_tools.logging import init_logging
from ds_tools.output import colored, uprint, Table, SimpleColumn, TableBar
from ds_tools.utils import num_suffix
from tz_aware_dt import localize

sys.path.append(Path(__file__).resolve().parents[1].joinpath('lib_old').as_posix())
from music_old import (
    iter_music_files, load_tags, iter_music_albums, iter_categorized_music_files, tag_repr, apply_mutagen_patches,
    TagException, iter_album_dirs, RM_TAGS_ID3, RM_TAGS_MP4, NoPrimaryArtistError, WikiSoundtrack
)
from music_old.constants import tag_name_map

log = logging.getLogger(__name__)

apply_mutagen_patches()


def parser():
    parser = ArgParser(description='Music Manager')

    info_parser = parser.add_subparser('action', 'info', help='Get song/tag information')
    info_parser.add_argument('path', nargs='+', help='One or more file/directory paths that contain music files')
    info_group = info_parser.add_mutually_exclusive_group()
    info_group.add_argument('--meta_only', '-m', action='store_true', help='Only show song metadata')
    info_group.add_argument('--count', '-c', action='store_true', help='Count tag types rather than printing all info')
    info_group.add_argument('--unique', '-u', metavar='TAGID', nargs='+', help='Count unique values of the specified tag(s)')
    info_group.add_argument('--tags', '-t', nargs='+', help='Filter tags to display in file info mode')
    info_group.add_argument('--table', '-T', action='store_true', help='Print a full table instead of individual tables per file')
    info_group.add_argument('--tag_table', '-TT', nargs='+', help='Print a table comparing the specified tag IDs across each file')

    rm_parser = parser.add_subparser('action', 'remove', help='Remove specified tags from the given files')
    rm_parser.add_argument('path', nargs='+', help='One or more file/directory paths that contain music files')
    rm_group = rm_parser.add_mutually_exclusive_group()
    rm_group.add_argument('--tags', '-t', nargs='+', help='One or more tag IDs to remove from the given files')
    rm_group.add_argument('--recommended', '-r', action='store_true', help='Remove recommended tags')

    cp_parser = parser.add_subparser('action', 'copy', help='Copy specified tags from one set of files to another')
    cp_parser.add_argument('--source', '-s', nargs='+', help='One or more file/directory paths that contain music files or ID3 info backups', required=True)
    cp_parser.add_argument('--dest', '-d', nargs='+', help='One or more file/directory paths that contain music files, or a path to store an ID3 info backup')
    cp_parser.add_argument('--backup', '-b', action='store_true', help='Store a backup of ID3 information instead of writing directly to matching music files')
    cp_parser.add_argument('--tags', '-t', nargs='+', help='One or more tag IDs to copy to the destination files')

    fix_parser = parser.add_subparser('action', 'fix', help='Fix poorly chosen tags in the given files (such as TXXX:DATE, etc)')
    fix_parser.add_argument('path', nargs='+', help='One or more file/directory paths that contain music files')

    sort_parser = parser.add_subparser('action', 'sort', help='Sort music into directories based on tag info')
    sort_parser.add_argument('path', help='A directory that contains directories that contain music files')

    wiki_sort_parser = parser.add_subparser('action', 'wiki_sort', help='Cleanup & sort files based on the information found when matching them to artists / albums / songs in various wikis')
    wiki_sort_parser.add_argument('source', metavar='path', help='A directory that contains directories that contain music files')
    wiki_sort_parser.add_argument('destination', metavar='path', nargs='?', help='The destination directory for the top-level artist directories of the sorted files')
    wiki_sort_parser.add_argument('--allow_no_dest', '-N', action='store_true', help='Allow sorting to continue even if there are some files that do not have a new destination')
    wiki_sort_parser.add_argument('--basic_cleanup', '-B', action='store_true', help='Only run basic cleanup tasks, no wiki updates')
    wiki_sort_parser.add_argument('--move_unknown', '-u', action='store_true', help='Move albums that would end up in the UNKNOWN_FIXME subdirectory')
    wiki_sort_parser.add_argument('--allow_incomplete', '-i', action='store_true', help='Allow updating tags when there is an incomplete match (such as artist but no album/song)')
    wiki_sort_parser.add_argument('--unmatched_cleanup', '-C', action='store_true', help='Run cleanup tasks for unmatched files (commonly OSTs/collaborations)')
    wiki_sort_parser.add_argument('--true_soloist', '-S', action='store_true', help='For solo artists, use only their name instead of including their group and do not sort them with their group')
    wiki_sort_parser.add_argument('--collab_mode', '-c', choices=('title', 'artist', 'both'), default='artist', help='List collaborators in the artist tag, the title tag, or both (default: %(default)s)')
    wiki_sort_parser.add_argument('--hide_edition', '-E', action='store_true', help='Exclude the edition from the album title, if present (default: include it)')
    wiki_sort_parser.add_argument('--no_ost_filter', '-F', action='store_true', help='Lookup full info for all OST albums (default: only those matching a file in the given path)')
    wiki_sort_parser.add_argument('--url', '-U', help='Force the given URL to be used as the match for the given source directory')

    p2t_parser = parser.add_subparser('action', 'path2tag', help='Update tags based on the path to each file')
    p2t_parser.add_argument('path', help='A directory that contains directories that contain music files')
    p2t_parser.add_argument('--title', '-t', action='store_true', help='Update title based on filename')

    set_parser = parser.add_subparser('action', 'set', help='Set the value of the given tag on all music files in the given path')
    set_parser.add_argument('path', nargs='+', help='One or more file/directory paths that contain music files')
    set_parser.add_argument('--tag', '-t', nargs='+', help='Tag ID(s) to modify', required=True)
    set_parser.add_argument('--value', '-V', help='Value to replace existing values with', required=True)
    set_parser.add_argument('--replace', '-r', nargs='+', help='If specified, only replace tag values that match the given patterns(s)')
    set_parser.add_argument('--partial', '-p', action='store_true', help='Update only parts of tags that match a pattern specified via --replace/-r')

    list_parser = parser.add_subparser('action', 'list', help='TEMP')
    list_parser.add_argument('path', help='A directory that contains directories that contain music files')

    auto_parser = parser.add_subparser('action', 'auto', help='Automatically perform the most common tasks')
    auto_parser.add_argument('path', help='A directory that contains directories that contain music files')

    match_parser = parser.add_subparser('action', 'match', help='Test matching files in the given directory to songs from wiki')
    match_parser.add_argument('path', help='A directory that contains directories that contain music files')
    match_parser.add_argument('--no_ost_filter', '-F', action='store_true', help='Lookup full info for all OST albums (default: only those matching a file in the given path)')

    wiki_list_parser = parser.add_subparser('action', 'wiki_list', help='List album/song metadata in the format expected in the wiki')
    wiki_list_parser.add_argument('path', help='A directory that contains directories that contain music files')

    parser.include_common_args('verbosity', 'dry_run')
    return parser


def main():
    args = parser().parse_args()
    init_logging(args.verbose, log_path=None, names=None)
    if args.verbose > 10:
        logging.getLogger('ds_tools.music.wiki.entities.scoring').setLevel(logging.DEBUG)

    if args.action == 'info':
        if args.count:
            count_tag_types(args.path)
        elif args.unique:
            count_unique_vals(args.path, args.unique)
        elif args.table:
            table_song_tags(args.path)
        elif args.tag_table:
            table_song_tags(args.path, args.tag_table)
        else:
            print_song_tags(args.path, args.tags, args.meta_only)
    elif args.action == 'auto':
        remove_tags(args.path, None, args.dry_run, True)    # remove . -r
        fix_tags(args.path, args.dry_run)                   # fix .
        sort_albums(args.path, args.dry_run)                # sort .
    elif args.action == 'remove':
        remove_tags(args.path, args.tags, args.dry_run, args.recommended)
    elif args.action == 'fix':
        fix_tags(args.path, args.dry_run)
    elif args.action == 'copy':
        if args.backup:
            if len(args.dest) > 1:
                raise ValueError('Only one --dest/-d path may be provided in backup mode')
            save_tag_backups(args.source, args.dest)
        else:
            copy_tags(args.source, args.dest, args.tags, args.dry_run)
    elif args.action == 'sort':
        sort_albums(args.path, args.dry_run)
    elif args.action == 'wiki_sort':
        sort_by_wiki(
            args.source, args.destination or args.source, args.allow_no_dest, args.basic_cleanup, args.move_unknown,
            args.allow_incomplete, args.unmatched_cleanup, args.true_soloist, args.collab_mode, args.hide_edition,
            args.dry_run, args.no_ost_filter, args.url
        )
    elif args.action == 'path2tag':
        path2tag(args.path, args.dry_run, args.title)
    elif args.action == 'set':
        set_tags(args.path, args.tag, args.value, args.replace, args.partial, args.dry_run)
    elif args.action == 'list':
        list_dir2artist(args.path)
    elif args.action == 'match':
        match_wiki(args.path, args.no_ost_filter)
    elif args.action == 'wiki_list':
        wiki_list(args.path)
    else:
        log.error('Unconfigured action')


def match_wiki(path, no_ost_filter):
    cyan = lambda raw, pre: colored(pre, 'cyan')
    green = lambda raw, pre: colored(pre, 'green')
    yellow = lambda raw, pre: colored(pre, 'yellow')

    tbl = Table(
        SimpleColumn('F.Artist', formatter=cyan), SimpleColumn('Wiki Artist', formatter=green),
        SimpleColumn('File Album', formatter=cyan), SimpleColumn('Wiki Album', formatter=green),
        SimpleColumn('A.Scr', formatter=yellow),
        # SimpleColumn('File Alb Type', formatter=cyan),
        SimpleColumn('Wiki Alb Type', formatter=green),
        SimpleColumn('F.Dsk', formatter=cyan), SimpleColumn('W.Dsk', formatter=green),
        SimpleColumn('F.Tr', formatter=cyan), SimpleColumn('W.Tr', formatter=green),
        SimpleColumn('File Title', formatter=cyan), SimpleColumn('Wiki Title', formatter=green),
        SimpleColumn('T.Scr', formatter=yellow),
        sort_by=('Wiki Artist', 'Wiki Album', 'F.Tr', 'F.Artist', 'File Album', 'File Title'),
        update_width=True
    )

    set_ost_filter(path, no_ost_filter)
    rows = []
    for music_file in iter_music_files(path):
        try:
            row = {}
            try:
                row['Wiki Artist'] = music_file.wiki_artist.qualname if music_file.wiki_artist else ''
            except NoPrimaryArtistError as e:
                row['Wiki Artist'] = '[no primary artist]'

            row.update({
                'F.Artist': music_file.tag_artist,
                # 'Wiki Artist': music_file.wiki_artist.qualname if music_file.wiki_artist else '',

                'File Album': music_file.album_name_cleaned,
                'Wiki Album': music_file.wiki_album.title() if music_file.wiki_album else '',
                'File Alb Type': music_file.album_type_dir,
                'Wiki Alb Type': music_file.wiki_album.album_type if music_file.wiki_album else '',
                'A.Scr': music_file.wiki_scores.get('album', -1),

                'File Title': music_file.tag_title,
                'Wiki Title': music_file.wiki_song.long_name if music_file.wiki_song else '',
                'T.Scr': music_file.wiki_scores.get('song', -1),

                # 'F.Tr': str(music_file.tag_text('track', default='')),
                'F.Tr': '{:>2d}'.format(int(music_file.track_num)) if music_file.track_num else '',
                'W.Tr': '{:>2d}'.format(int(music_file.wiki_song.num)) if music_file.wiki_song else '',
                # 'F.Tr': str(music_file.track_num),
                # 'W.Tr': str(music_file.wiki_song.num) if music_file.wiki_song else '',

                # 'F.Dsk': str(music_file.tag_text('disk', default='')),
                'F.Dsk': '{:>2d}'.format(int(music_file.disk_num)) if music_file.disk_num else '',
                # 'F.Dsk': str(music_file.disk_num),
                'W.Dsk': '{:>2d}'.format(int(music_file.wiki_song.disk)) if music_file.wiki_song else '',
                # 'W.Dsk': str(music_file.wiki_song.disk) if music_file.wiki_song else '',
            })
        except Exception as e:
            log.error('Error processing {}: {}'.format(music_file, e), extra={'color': (15, 9)})
            log.log(19, traceback.format_exc())
        else:
            rows.append(row)

    tbl.print_rows(rows)


def list_dir2artist(path):
    tools_dir = Path(__file__).expanduser().resolve().parents[1].as_posix()
    with open(os.path.join(tools_dir, 'music', 'artist_dir_to_artist.json'), 'r', encoding='utf-8') as f:
        dir2artist = json.load(f)

    for _dir, disp_name in sorted(dir2artist.items()):
        if not disp_name:
            artist_dir = os.path.join(path, _dir)
            if os.path.exists(artist_dir):
                for mfile in iter_music_files(artist_dir):
                    try:
                        artist = mfile.tags['TPE1'].text[0]
                    except KeyError as e:
                        pass
                    else:
                        if ',' not in artist:
                            uprint('"{}": "{}",'.format(_dir, artist))
                            break
            else:
                uprint('"{}": "{}",'.format(_dir, ''))
        else:
            uprint('"{}": "{}",'.format(_dir, disp_name))


def path2tag(path, dry_run, incl_title):
    """
    Update tags based on the path to each file

    :param str path: A directory that contains directories that contain music files
    :param bool dry_run: Print the actions that would be taken instead of taking them
    :param bool incl_title: Update title based on filename
    """
    # TODO: Add prompt / default yes for individual files
    prefix = '[DRY RUN] Would update' if dry_run else 'Updating'

    for music_file in iter_music_files(path):
        try:
            title = music_file.tag_title
        except TagException as e:
            log.warning('Skipping due to {}: {}'.format(type(e).__name__, e))
            continue

        filename = music_file.basename(True, True)
        if incl_title and (title != filename):
            log.info('{} the title of {} from {!r} to {!r}'.format(prefix, music_file.filename, title, filename))
            if not dry_run:
                music_file.set_title(filename)
                music_file.save()
        else:
            log.log(19, 'Skipping file with already correct title: {}'.format(music_file.filename))


def sort_albums(path, dry_run):
    """
    Sort albums in the given path by album type

    :param str path: Path to the directory to sort
    :param bool dry_run: Print the actions that would be taken instead of taking them
    """
    prefix, verb = ('[DRY RUN] ', 'Would rename') if dry_run else ('', 'Renaming')
    punc_strip_tbl = str.maketrans({c: '' for c in string.punctuation})

    for parent_dir, album_dir, music_files in iter_music_albums(path):
        if not album_dir.startswith('['):
            album_path = os.path.join(parent_dir, album_dir)
            try:
                dates = {f.tag_text('date') for f in music_files}
            except TagException as e:
                log.warning('Skipping dir {!r} due to problem finding date: {}'.format(album_path, e))
            else:
                album_date = None
                dates = {d for d in dates if d}
                if len(dates) == 1:
                    date_str = dates.pop().translate(punc_strip_tbl)[:8]
                    date_fmt_in = '%Y' if len(date_str) == 4 else '%Y%m%d'
                    date_fmt_out = '%Y' if len(date_str) == 4 else '%Y.%m.%d'
                    try:
                        album_date = localize(date_str, in_fmt=date_fmt_in, out_fmt=date_fmt_out)
                    except Exception as e:
                        log.warning('Error localizing album date for {!r}: {}'.format(album_path, e))
                else:
                    log.warning('Unexpected dates found in album {!r}: {}'.format(album_path, ', '.join(sorted(dates))))

                if album_date:
                    album_dir = '[{}] {}'.format(album_date, album_dir)
                    new_path = os.path.join(parent_dir, album_dir)
                    log.info('[add date] {}{} {!r} -> {!r}'.format(prefix, verb, album_path, new_path))
                    if not dry_run:
                        os.rename(album_path, new_path)

    numbered_albums = defaultdict(lambda: defaultdict(dict))
    for parent_dir, artist_dir, category_dir, album_dir, music_files in iter_categorized_music_files(path):
        album_path = os.path.join(parent_dir, artist_dir, category_dir, album_dir)
        if (category_dir in ('Albums', 'Mini Albums')) and album_dir.startswith('['):
            album_dir_lower = album_dir.lower()
            if any(skip_reason in album_dir_lower for skip_reason in ('summer mini album', 'reissue', 'repackage')):
                log.debug('Skipping non-standard album: {}'.format(album_dir))
                continue
            category = category_dir[:-1]

            files, japanese = 0, 0
            for music_file in music_files:
                files += 1
                _tags = {'genre': [], 'title': [], 'album': []}
                for tag_name in _tags:
                    _tags[tag_name] = [t.translate(punc_strip_tbl).lower() for t in music_file.all_tag_text(tag_name)]

                if any(i in tag for tag_list in _tags.values() for tag in tag_list for i in ('jpop', 'japanese')):
                    japanese += 1

            log.debug('{}: Japanese: {:.2%}'.format(album_path, japanese / files))
            if japanese / files >= .45:
                category = 'Japanese {}'.format(category)

            num = len(numbered_albums[artist_dir][category]) + 1
            numbered_albums[artist_dir][category][num] = album_path

    for artist_dir, categorized_albums in sorted(numbered_albums.items()):
        for cat, albums in sorted(categorized_albums.items()):
            for num, _path in sorted(albums.items()):
                if not _path.endswith(']'):
                    parent_dir, album_dir = os.path.split(_path)
                    album_dir = '{} [{}{} {}]'.format(album_dir, num, num_suffix(num), cat)
                    new_path = os.path.join(parent_dir, album_dir)
                    log.info('[Number within category] {}{} {!r} -> {!r}'.format(prefix, verb, _path, new_path))
                    if not dry_run:
                        os.rename(_path, new_path)
                else:
                    log.log(19, 'Album already has correct name: {}'.format(_path))

    for parent_dir, artist_dir, category_dir, album_dir, music_files in iter_categorized_music_files(path):
        album_path = os.path.join(parent_dir, artist_dir, category_dir, album_dir)
        pat = '^(\[[^\]]+\])?\s*' + artist_dir + '\s*-?\s*(.*)$'
        m = re.match(pat, album_dir)
        if m:
            date_prefix = m.group(1)
            album_name = m.group(2).strip()
            new_album_dir = album_name if not date_prefix else '{} {}'.format(date_prefix, album_name)
            # new_album_dir = m.group(1).strip()
            if new_album_dir:
                new_album_path = os.path.join(parent_dir, artist_dir, category_dir, new_album_dir)
                if new_album_path != album_path:
                    log.info('[Remove artist from album dir name] {}{} {!r} -> {!r}'.format(prefix, verb, album_path, new_album_path))
                    if not dry_run:
                        os.rename(album_path, new_album_path)


def wiki_list(path):
    """
    List album/song metadata in the format expected in the wiki

    :param str path: A directory that contains directories that contain music files
    """
    # Note: using log instead of print since it's configured to use UTF-8 already
    for i, album_dir in enumerate(iter_album_dirs(path)):
        if i:
            log.info('\n')

        log.info('{} - {} - {} - Length: {}'.format(
            album_dir.artist_path.name, album_dir._type_path.name, album_dir.name, album_dir.length_str
        ))
        log.info('=' * 120)
        for song in album_dir:
            log.info('#"{}" - {}'.format(song.tag_title, song.length_str))


def set_ost_filter(path, no_ost_filter=False):
    if no_ost_filter:
        WikiSoundtrack._search_filters = None
    else:
        ost_filter = set()
        for f in iter_music_files(path):
            ost_filter.add(f.album_name_cleaned)
            ost_filter.add(f.dir_name_cleaned)

        WikiSoundtrack._search_filters = ost_filter

    log.debug('OST Search Filter: {}'.format(WikiSoundtrack._search_filters))


def sort_by_wiki(
    source_path, dest_dir, allow_no_dest, basic_cleanup, move_unknown, allow_incomplete, unmatched_cleanup,
    true_soloist, collab_mode, hide_edition, dry_run, no_ost_filter, url=None
):
    """
    Cleanup & sort files based on the information found when matching them to artists / albums / songs in various wikis

    :param str source_path: A directory that contains directories that contain music files
    :param str dest_dir: The destination directory for the top-level artist directories of the sorted files
    :param bool allow_no_dest: Allow sorting to continue even if there are some files that do not have a new destination
    :param bool basic_cleanup: Only run basic cleanup tasks, no wiki updates (remove bad tags, fix tags using outdated
      tag types, remove URLs from the end of lyrics, etc).  These actions are still performed during a normal run -
      specifying this argument only skips the steps that would come after this cleanup.
    :param bool move_unknown: Move albums that would end up in the UNKNOWN_FIXME subdirectory
    :param bool allow_incomplete: Allow updating tags when there is an incomplete match (such as artist but no
      album/song)
    :param bool unmatched_cleanup: Run cleanup tasks for unmatched files (commonly OSTs/collaborations)
    :param bool true_soloist: For solo artists, use only their name instead of including their group, and do not sort
      them with their group
    :param str collab_mode: List collaborators in the artist tag, the title tag, or both
    :param bool hide_edition: Exclude the edition from the album title, if present (default: include it)
    :param bool dry_run: Print the actions that would be taken instead of taking them
    :param bool no_ost_filter:
    :param str|None url: Force the given URL to be used as the match for the given source directory
    """
    _dest_dir = dest_dir
    mv_prefix = '[DRY RUN] Would move' if dry_run else 'Moving'
    rm_prefix = '[DRY RUN] Would remove' if dry_run else 'Removing'
    dest_root = Path(dest_dir).expanduser().resolve()
    cwd = Path('.').resolve()

    set_ost_filter(source_path, no_ost_filter)

    unplaced = 0
    dests = {}
    conflicts = {}
    exists = set()
    album_dirs = []
    for i, album_dir in enumerate(iter_album_dirs(source_path)):
        if url and i:
            raise ValueError('Please specify only a single album directory when using --url / -U')
        album_dirs.append(album_dir)
        album_dir.remove_bad_tags(dry_run)
        album_dir.fix_song_tags(dry_run)
        if basic_cleanup:
            continue

        rel_path = album_dir.expected_rel_path(true_soloist, hide_edition)
        if rel_path and ('UNKNOWN_FIXME' in rel_path.as_posix()) and not move_unknown:
            log.log(19, 'Skipping {} because a proper location could not be determined'.format(album_dir))
            continue

        if rel_path is not None:
            if source_path == _dest_dir:
                dest_dir = album_dir.artist_path.parent.joinpath(rel_path)
            else:
                dest_dir = dest_root.joinpath(rel_path)

            if dest_dir.exists():
                if not album_dir.path.samefile(dest_dir):
                    log.warning('Dir already exists at destination for {}: {!r}'.format(album_dir, dest_dir.as_posix()), extra={'color': 'yellow'})
                    exists.add(dest_dir)
                else:
                    log.log(19, 'Album already has the correct path: {}'.format(album_dir))
                    continue

            if dest_dir in dests:
                log.warning('Duplicate destination conflict for {}: {!r}'.format(album_dir, dest_dir.as_posix()), extra={'color': 'yellow'})
                conflicts[album_dir] = dest_dir
                conflicts[dests[dest_dir]] = dest_dir
            else:
                dests[dest_dir] = album_dir
        else:
            log.warning('Could not determine placement for {}'.format(album_dir), extra={'red': True})
            unplaced += 1

    if basic_cleanup:
        return

    if unplaced and not allow_no_dest:
        raise RuntimeError('Unable to determine placement for {:,d} albums - exiting'.format(unplaced))

    if exists:
        raise RuntimeError('Directories already exist in {:,d} destinations - choose another destination directory'.format(len(exists)))
    elif conflicts:
        raise RuntimeError('There are {:,d} duplicate destination conflicts - exiting'.format(len(conflicts)))

    for dest_dir, album_dir in sorted(dests.items()):
        try:
            rel_path = dest_dir.relative_to(cwd).as_posix()
        except Exception as e:
            rel_path = dest_dir.as_posix()
        log.info('{} {!r} -> {!r}'.format(mv_prefix, album_dir, rel_path))
        if not dry_run:
            album_dir.move(dest_dir)

    src_path = Path(source_path).expanduser().resolve()
    if src_path.is_dir():
        for p in src_path.iterdir():
            if p.is_dir() and not list(p.iterdir()):
                log.info('{} empty directory: {}'.format(rm_prefix, p.as_posix()))
                if not dry_run:
                    p.rmdir()

    dest_root = None if source_path == _dest_dir else dest_root
    logged_messages = 0
    for i, album_dir in enumerate(album_dirs):
        if i and logged_messages:
            print()
        logged_messages = album_dir.update_song_tags_and_names(
            allow_incomplete, true_soloist, collab_mode, dry_run, dest_root, hide_edition, url
        )
        if unmatched_cleanup and not album_dir.wiki_album:
            if logged_messages:
                print()
            logged_messages = album_dir.cleanup_partial_matches(dry_run)

    if src_path.is_dir() and not list(src_path.iterdir()):
        log.info('{} empty directory: {}'.format(rm_prefix, src_path.as_posix()))
        if not dry_run:
            src_path.rmdir()


def set_tags(paths, tag_ids, value, replace_pats, partial, dry_run):
    prefix, repl_msg, set_msg = ('[DRY RUN] ', 'Would replace', 'Would set') if dry_run else ('', 'Replacing', 'Setting')
    repl_rxs = [re.compile(fnpat2re(pat)[4:-3]) for pat in replace_pats] if replace_pats else []
    if partial and not repl_rxs:
        raise ValueError('When using --partial/-p, --replace/-r must also be specified')

    for music_file in iter_music_files(paths):
        if not isinstance(music_file.tags, ID3):
            log.debug('Skipping non-MP3: {}'.format(music_file.filename))
            continue

        should_save = False
        for tag_id in tag_ids:
            tag_name = tag_name_map.get(tag_id)
            if not tag_name:
                raise ValueError('Invalid tag ID: {}'.format(tag_id))

            current_vals = music_file.tags_for_id(tag_id)
            if not current_vals:
                if music_file.ext == 'mp3':
                    try:
                        fcls = getattr(mutagen.id3._frames, tag_id.upper())
                    except AttributeError as e:
                        raise ValueError('Invalid tag ID: {} (no frame class found for it)'.format(tag_id)) from e
                else:
                    raise ValueError('Adding new tags to non-MP3s is not currently supported for {}'.format(music_file))

                log.info('{}{} {}/{} = {!r} in file: {}'.format(prefix, set_msg, tag_id, tag_name, value, music_file.filename))
                should_save = True
                if not dry_run:
                    music_file.tags.add(fcls(text=value))
            else:
                if len(current_vals) > 1:
                    log.warning('Skipping file with multiple values for {}/{}: {}'.format(tag_id, tag_name, music_file.filename))

                current_val = current_vals[0]
                current_text = current_val.text[0]
                new_text = current_text
                if partial:
                    for rx in repl_rxs:
                        new_text = rx.sub(value, new_text)
                else:
                    if repl_rxs:
                        if any(rx.search(current_text) for rx in repl_rxs):
                            new_text = value
                    else:
                        new_text = value

                if new_text != current_text:
                    log.info('{}{} {}/{} {!r} with {!r} in {}'.format(prefix, repl_msg, tag_id, tag_name, current_text, new_text, music_file.filename))
                    should_save = True
                    if not dry_run:
                        current_vals[0].text[0] = new_text

        if should_save:
            if not dry_run:
                music_file.save()
        else:
            log.log(19, 'Nothing to change for {}'.format(music_file.filename))


def fix_tags(paths, dry_run):
    # TODO: Convert ` to '
    prefix, add_msg, rmv_msg = ('[DRY RUN] ', 'Would add', 'remove') if dry_run else ('', 'Adding', 'removing')
    upd_msg = 'Would update' if dry_run else 'Updating'

    for music_file in iter_music_files(paths):
        if music_file.ext != 'mp3':
            log.debug('Skipping non-MP3: {}'.format(music_file))
            continue

        tdrc = music_file.tags.getall('TDRC')
        txxx_date = music_file.tags.getall('TXXX:DATE')
        if (not tdrc) and txxx_date:
            file_date = txxx_date[0].text[0]

            log.info('{}{} TDRC={} to {} and {} its TXXX:DATE tag'.format(prefix, add_msg, file_date, music_file.filename, rmv_msg))
            if not dry_run:
                music_file.tags.add(TDRC(text=file_date))
                music_file.tags.delall('TXXX:DATE')
                music_file.save()

        changes = 0
        for uslt in music_file.tags.getall('USLT'):
            m = re.match('^(.*)(https?://\S+)$', uslt.text, re.DOTALL)
            if m:
                # noinspection PyUnresolvedReferences
                new_lyrics = m.group(1).strip() + '\r\n'
                log.info('{}{} lyrics for {} from {!r} to {!r}'.format(prefix, upd_msg, music_file.filename, tag_repr(uslt.text), tag_repr(new_lyrics)))
                if not dry_run:
                    uslt.text = new_lyrics
                    changes += 1

        if changes and not dry_run:
            log.info('Saving changes to lyrics in {}'.format(music_file))
            music_file.save()

    for music_file in iter_music_files(paths):
        wiki_artist = music_file.wiki_artist
        if wiki_artist is not None:
            try:
                album_name = music_file.album_name_cleaned
            except KeyError as e:
                log.error('Error retrieving album for {}'.format(music_file), extra={'red': True})
                raise e
            wiki_album = music_file.wiki_album
            if wiki_album is not None:
                wiki_song = music_file.wiki_song
                if wiki_song is not None:
                    song_title = music_file.tag_title
                    if (song_title.lower() != wiki_song.file_title.lower()) and not song_title.lower().startswith(wiki_song.file_title.lower()):
                        log.info('{}{} {!r}/{!r}/{!r} ==> {!r} / {}'.format(prefix, upd_msg, music_file.tag_artist, album_name, song_title, wiki_song.file_title, wiki_song))
                        if not dry_run:
                            try:
                                music_file.set_title(wiki_song.file_title)
                            except TagException as e:
                                log.error(e)
                            else:
                                music_file.save()
                    else:
                        log.log(19, 'No changes necessary for {!r}/{!r}/{!r} == {!r} / {}'.format(music_file.tag_artist, album_name, song_title, wiki_song.file_title, wiki_song))
                else:
                    log.error('Unable to find song for {} in wiki'.format(music_file), extra={'red': True})
            else:
                log.error('Unable to find album for {} in wiki'.format(music_file), extra={'red': True})
        else:
            log.error('Unable to find artist for {} in wiki'.format(music_file), extra={'red': True})


def copy_tags(source_paths, dest_paths, tags, dry_run):
    if not tags:
        raise ValueError('One or more tags or \'ALL\' must be specified for --tags/-t')
    tags = sorted({tag.upper() for tag in tags})
    all_tags = 'ALL' in tags
    src_tags = load_tags(source_paths)

    prefix, verb = ('[DRY RUN] ', 'Would update') if dry_run else ('', 'Updating')

    for music_file in iter_music_files(dest_paths):
        path = music_file.filename
        content_hash = music_file.tagless_sha256sum()
        if content_hash in src_tags:
            if all_tags:
                log.info('{}{} all tags in {}'.format(prefix, verb, path))
                if not dry_run:
                    log.info('Saving changes to {}'.format(path))
                    src_tags[content_hash].save(path)
            else:
                do_save = False
                for tag in tags:
                    tag_name = tag_name_map.get(tag, '[unknown]')
                    tag_str = '{} ({})'.format(tag, tag_name)
                    src_vals = src_tags[content_hash].getall(tag)
                    if not src_vals:
                        log.info('{}: No value found in source for {}'.format(path, tag_str))
                    else:
                        dest_vals = music_file.tags.getall(tag)
                        if src_vals == dest_vals:
                            log.info('{}: Source and dest values match for {}'.format(path, tag_str))
                        else:
                            dest_val_str = ', '.join(map(tag_repr, dest_vals))
                            src_val_str = ', '.join(map(tag_repr, src_vals))
                            log.info('{}{} {} in {} from [{}] to [{}]'.format(prefix, verb, tag_str, path, dest_val_str, src_val_str))
                            if not dry_run:
                                music_file.tags.setall(tag, src_vals)
                                do_save = True
                if do_save:
                    log.info('Saving changes to {}'.format(path))
                    music_file.tags.save(path)
        else:
            log.info('{}: sha256sum not found in source paths'.format(music_file.filename))


def save_tag_backups(source_paths, backup_path):
    if isinstance(backup_path, (list, tuple)):
        backup_path = backup_path[0]
    if not backup_path:
        backup_path = '/var/tmp/id3_tags.pickled'
    log.info('backup_path: {}'.format(backup_path))

    backup_path = os.path.expanduser(backup_path)
    if os.path.exists(backup_path) and os.path.isdir(backup_path):
        backup_path = os.path.join(backup_path, 'id3_tags.pickled')

    tag_info = load_tags([backup_path]) if os.path.isfile(backup_path) else {}
    for i, music_file in enumerate(iter_music_files(source_paths, include_backups=True)):
        content_hash = music_file.tagless_sha256sum()
        log.debug('{}: {}'.format(music_file.filename, content_hash))
        tag_info[content_hash] = music_file.tags

    with open(backup_path, 'wb') as f:
        log.info('Writing tag info to: {}'.format(backup_path))
        pickle.dump(tag_info, f)


def remove_tags(paths, tag_ids, dry_run, recommended):
    prefix, verb = ('[DRY RUN] ', 'Would remove') if dry_run else ('', 'Removing')

    # tag_ids = sorted({tag_id.upper() for tag_id in tag_ids})
    tag_id_pats = sorted({tag_id for tag_id in tag_ids}) if tag_ids else []
    if tag_id_pats:
        log.info('{}{} the following tags from all files:'.format(prefix, verb))
    if tag_ids:
        for tag_id in tag_ids:
            log.info('\t{}: {}'.format(tag_id, tag_name_map.get(tag_id, '[unknown]')))

    i = 0
    for music_file in iter_music_files(paths):
        if isinstance(music_file.tags, MP4Tags):
            if recommended:
                tag_id_pats = RM_TAGS_MP4
            # file_tag_ids = {tag_id.upper(): tag_id for tag_id in music_file.tags}
        elif isinstance(music_file.tags, ID3):
            if recommended:
                tag_id_pats = RM_TAGS_ID3
        else:
            raise TypeError('Unhandled tag type: {}'.format(type(music_file.tags).__name__))

        to_remove = {}
        for tag, val in sorted(music_file.tags.items()):
            if any(fnmatch(tag, pat) for pat in tag_id_pats):
                to_remove[tag] = val if isinstance(val, list) else [val]

        if to_remove:
            if i:
                log.debug('')
            rm_str = ', '.join(
                '{}: {}'.format(tag_id, tag_repr(val)) for tag_id, vals in sorted(to_remove.items()) for val in vals
            )
            info_str = ', '.join('{} ({})'.format(tag_id, len(vals)) for tag_id, vals in sorted(to_remove.items()))

            log.info('{}{}: {} tags: {}'.format(prefix, music_file.filename, verb, info_str))
            log.debug('\t{}: {}'.format(music_file.filename, rm_str))
            if not dry_run:
                for tag_id in to_remove:
                    if isinstance(music_file.tags, MP4Tags):
                        del music_file.tags[tag_id]
                    elif isinstance(music_file.tags, ID3):
                        music_file.tags.delall(tag_id)
                music_file.save()
            i += 1
        else:
            log.debug('{}: Did not have the tags specified for removal'.format(music_file.filename))

    if not i:
        log.info('None of the provided files had the specified tags')


def table_song_tags(paths, include_tags=None):
    rows = [TableBar()]
    tags = set()
    for music_file in iter_music_files(paths, include_backups=True):
        row = defaultdict(str, path=music_file.filename)
        for tag, val in sorted(music_file.tags.items()):
            tag = ':'.join(tag.split(':')[:2])
            if (include_tags is None) or (tag in include_tags):
                tags.add(tag)
                row[tag] = tag_repr(str(val), 10, 5) if tag.startswith('APIC') else tag_repr(str(val))
        rows.append(row)

    desc_row = {tag: tag_name_map.get(tag[:4], '[unknown]') for tag in tags}
    desc_row['path'] = '[Tag Description]'
    rows.insert(0, desc_row)
    cols = [SimpleColumn(tag) for tag in sorted(tags)]
    tbl = Table(SimpleColumn('path'), *cols, update_width=True)
    tbl.print_rows(rows)


def print_song_tags(paths, tags, meta_only=False):
    tags = {tag.upper() for tag in tags} if tags else None
    for i, music_file in enumerate(iter_music_files(paths, include_backups=True)):
        if i and not meta_only:
            print()

        if isinstance(music_file.tags, MP4Tags):
            uprint('{} [{}] (MP4):'.format(music_file.filename, music_file.length_str))
        elif isinstance(music_file.tags, ID3):
            uprint('{} [{}] (ID3v{}.{}):'.format(music_file.filename, music_file.length_str, *music_file.tags.version[:2]))
        else:
            raise TypeError('Unhandled tag type: {}'.format(type(music_file.tags).__name__))

        if meta_only:
            continue

        tbl = Table(SimpleColumn('Tag'), SimpleColumn('Tag Name'), SimpleColumn('Value'), update_width=True)
        rows = []
        for tag, val in sorted(music_file.tags.items()):
            if len(tag) > 4:
                tag = tag[:4]

            if not tags or (tag in tags):
                rows.append({'Tag': tag, 'Tag Name': tag_name_map.get(tag, '[unknown]'), 'Value': tag_repr(str(val))})
        if rows:
            tbl.print_rows(rows)


def count_unique_vals(paths, tag_ids):
    include = {tag_id.upper() for tag_id in tag_ids}
    if not include:
        raise ValueError('Unable to count unique values of tags if no tag IDs were provided')

    unique_vals = defaultdict(Counter)
    for music_file in iter_music_files(paths):
        for tag, val in music_file.tags.items():
            tag = tag[:4]
            for pattern in include:
                if fnmatch(tag, pattern):
                    unique_vals[tag][str(val)] += 1
                    break

    tbl = Table(
        SimpleColumn('Tag'), SimpleColumn('Tag Name'), SimpleColumn('Count', align='>', ftype=',d'),
        SimpleColumn('Value'), update_width=True
    )
    rows = []
    for tag, val_counter in unique_vals.items():
        for val, count in val_counter.items():
            rows.append({
                'Tag': tag, 'Tag Name': tag_name_map.get(tag, '[unknown]'), 'Count': count, 'Value': tag_repr(val)
            })
    tbl.print_rows(rows)


def count_tag_types(paths):
    total_tags = Counter()
    unique_tags = Counter()
    unique_values = defaultdict(Counter)
    id3_versions = Counter()
    files = 0
    for music_file in iter_music_files(paths):
        files += 1
        tag_set = set()
        for tag, val in music_file.tags.items():
            tag = tag[:4]
            tag_set.add(tag)
            total_tags[tag] += 1
            unique_values[tag][str(val)] += 1

        unique_tags.update(tag_set)
        if isinstance(music_file.tags, MP4Tags):
            pass
        elif isinstance(music_file.tags, ID3):
            id3_versions.update(['ID3v{}.{}'.format(*music_file.tags.version[:2])])
        else:
            log.warning('{}: Unhandled tag type: {}'.format(music_file.filename, type(music_file.tags).__name__))

    tag_rows = []
    for tag in unique_tags:
        tag_rows.append({
            'Tag': tag, 'Tag Name': tag_name_map.get(tag, '[unknown]'), 'Total': total_tags[tag],
            'Files': unique_tags[tag], 'Files %': unique_tags[tag]/files,
            'Per File (overall)': total_tags[tag]/files, 'Per File (with tag)': total_tags[tag]/unique_tags[tag],
            'Unique Values': len(unique_values[tag])
        })

    tbl = Table(
        SimpleColumn('Tag'), SimpleColumn('Tag Name'), SimpleColumn('Total', align='>', ftype=',d'),
        SimpleColumn('Files', align='>', ftype=',d'), SimpleColumn('Files %', align='>', ftype=',.0%'),
        SimpleColumn('Per File (overall)', align='>', ftype=',.2f'),
        SimpleColumn('Per File (with tag)', align='>', ftype=',.2f'),
        SimpleColumn('Unique Values', align='>', ftype=',d'),
        update_width=True, sort_by='Tag'
    )
    tbl.print_rows(tag_rows)

    print()
    tbl = Table(SimpleColumn('Version'), SimpleColumn('Count'), update_width=True, sort_by='Version')
    tbl.print_rows([{'Version': ver, 'Count': count} for ver, count in id3_versions.items()])


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print()