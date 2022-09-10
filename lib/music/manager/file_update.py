"""
:author: Doug Skrypa
"""

import logging
import re
from fnmatch import translate as fnmatch_to_regex_str
from functools import partial
from multiprocessing import Pool
from typing import Iterable

from ds_tools.fs.paths import Paths
from ds_tools.input import get_input
from ds_tools.logging import init_logging, ENTRY_FMT_DETAILED_PID
from ..files.album import iter_album_dirs, iter_albums_or_files
from ..files.exceptions import TagException
from ..files.track.track import iter_music_files, SongFile

__all__ = ['path_to_tag', 'update_tags_with_value', 'clean_tags', 'remove_tags', 'add_track_bpm']
log = logging.getLogger(__name__)


def update_tags_with_value(
    paths: Paths,
    tag_ids: Iterable[str],
    value: str,
    replace_pats: Iterable[str] = None,
    partial: bool = False,  # noqa
    dry_run: bool = False,
    regex: bool = False,
):
    if replace_pats:
        if not regex:
            replace_pats = (fnmatch_to_regex_str(pat)[4:-3] for pat in replace_pats)

        patterns = [re.compile(pat) for pat in replace_pats]
    else:
        patterns = []

    if partial and not patterns:
        raise ValueError('When using --partial/-p, --replace/-r must also be specified')

    for n, music_obj in enumerate(iter_albums_or_files(paths)):
        if n:
            print()

        music_obj.update_tags_with_value(tag_ids, value, patterns=patterns, partial=partial, dry_run=dry_run)


def path_to_tag(paths: Paths, dry_run: bool = False, skip_prompt: bool = False, title: bool = False):
    """
    Update tags based on the path to each file

    :param paths: A directory that contains directories that contain music files
    :param dry_run: Print the actions that would be taken instead of taking them
    :param skip_prompt: Skip the prompt asking if a given file should be updated
    :param title: Update title based on filename
    """
    prefix = '[DRY RUN] Would update' if dry_run else 'Update'
    for music_file in iter_music_files(paths):
        try:
            tag_title = music_file.tag_title
        except TagException as e:
            log.warning(f'Skipping due to {e.__class__.__name__}: {e}')
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


def clean_tags(paths: Paths, dry_run: bool = False, add_bpm: bool = False, verbosity: int = 0):
    for album_dir in iter_album_dirs(paths):
        album_dir.remove_bad_tags(dry_run)
        album_dir.fix_song_tags(dry_run, add_bpm=False)

    if add_bpm:
        add_track_bpm(paths, dry_run=dry_run, verbosity=verbosity)


def remove_tags(paths: Paths, tag_ids: Iterable[str], dry_run: bool = False, remove_all: bool = False):
    for music_file in iter_music_files(paths):
        music_file.remove_tags(tag_ids, dry_run, logging.INFO, remove_all)


def add_track_bpm(paths: Paths, parallel: int = 4, dry_run: bool = False, verbosity: int = 0):
    _init_logging = partial(init_logging, verbosity, log_path=None, names=None, entry_fmt=ENTRY_FMT_DETAILED_PID)
    add_bpm_func = partial(_add_bpm, dry_run=dry_run)
    # Using a list instead of an iterator because pool.map needs to be able to chunk the items
    tracks = [f for f in iter_music_files(paths) if f.tag_type != 'vorbis']
    # May result in starvation if one proc finishes first due to less work, but it's simpler than a queue-based approach
    with Pool(parallel, _init_logging) as pool:
        pool.map(add_bpm_func, tracks)


def _add_bpm(track: SongFile, dry_run: bool = False):
    prefix, add_msg = ('[DRY RUN] ', 'Would add') if dry_run else ('', 'Adding')
    bpm = track.bpm(False, False)
    if bpm is None or bpm == 0:
        bpm = track.bpm(not dry_run, calculate=True)
        level, message = 20, f'{prefix}{add_msg} BPM={bpm} to {track}'
    else:
        level, message = 19, f'{track} already has BPM={bpm}'

    log.log(level, message)
    return message
