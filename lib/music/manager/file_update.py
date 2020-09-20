"""
:author: Doug Skrypa
"""

import logging
import re
from fnmatch import translate as fnmatch_to_regex_str
from functools import partial
from multiprocessing import Pool

from ds_tools.fs.paths import Paths
from ds_tools.input import get_input
from ds_tools.logging import init_logging, ENTRY_FMT_DETAILED_PID
from ..files.album import iter_album_dirs, iter_albums_or_files
from ..files.exceptions import TagException
from ..files.track.track import iter_music_files, SongFile

__all__ = ['path_to_tag', 'update_tags_with_value', 'clean_tags', 'remove_tags', 'add_track_bpm']
log = logging.getLogger(__name__)


def update_tags_with_value(paths: Paths, tag_ids, value, replace_pats=None, partial=False, dry_run=False):
    patterns = [re.compile(fnmatch_to_regex_str(pat)[4:-3]) for pat in replace_pats] if replace_pats else []
    if partial and not patterns:
        raise ValueError('When using --partial/-p, --replace/-r must also be specified')

    for music_obj in iter_albums_or_files(paths):
        music_obj.update_tags_with_value(tag_ids, value, patterns=patterns, partial=partial, dry_run=dry_run)


def path_to_tag(paths: Paths, dry_run=False, skip_prompt=False, title=False):
    """
    Update tags based on the path to each file

    :param paths: A directory that contains directories that contain music files
    :param bool dry_run: Print the actions that would be taken instead of taking them
    :param bool skip_prompt: Skip the prompt asking if a given file should be updated
    :param bool title: Update title based on filename
    """
    prefix = '[DRY RUN] Would update' if dry_run else 'Update'
    for music_file in iter_music_files(paths):
        try:
            tag_title = music_file.tag_title
        except TagException as e:
            log.warning('Skipping due to {}: {}'.format(type(e).__name__, e))
            continue

        filename = music_file.basename(True, True)
        if title and tag_title != filename:
            msg = f'{prefix} the title of {music_file.filename} from {tag_title!r} to {filename!r}'
            if dry_run:
                log.info(msg)
            elif get_input(msg + '? ', skip_prompt):
                music_file.tag_title = filename
                music_file.save()
        else:
            log.log(19, f'Skipping file with already correct title: {music_file.filename}')


def clean_tags(paths: Paths, dry_run=False, add_bpm=False, verbosity=0):
    for album_dir in iter_album_dirs(paths):
        album_dir.remove_bad_tags(dry_run)
        album_dir.fix_song_tags(dry_run, add_bpm=False)

    if add_bpm:
        add_track_bpm(paths, dry_run=dry_run, verbosity=verbosity)


def remove_tags(paths: Paths, tag_ids, dry_run=False, remove_all=False):
    for music_file in iter_music_files(paths):
        music_file.remove_tags(tag_ids, dry_run, logging.INFO, remove_all)


def add_track_bpm(paths: Paths, parallel=4, dry_run=False, verbosity=0):
    _init_logging = partial(init_logging, verbosity, log_path=None, names=None, entry_fmt=ENTRY_FMT_DETAILED_PID)
    add_bpm_func = partial(_add_bpm, dry_run=dry_run)
    # Using a list instead of an iterator because pool.map needs to be able to chunk the items
    tracks = [f for f in iter_music_files(paths) if f.tag_type != 'flac']
    # May result in starvation if one proc finishes first due to less work, but it's simpler than a queue-based approach
    with Pool(parallel, _init_logging) as pool:
        pool.map(add_bpm_func, tracks)


def _add_bpm(track: SongFile, dry_run=False):
    prefix, add_msg = ('[DRY RUN] ', 'Would add') if dry_run else ('', 'Adding')
    bpm = track.bpm(False, False)
    if bpm is None:
        bpm = track.bpm(not dry_run, calculate=True)
        log.info(f'{prefix}{add_msg} BPM={bpm} to {track}')
    else:
        log.log(19, f'{track} already has BPM={bpm}')
