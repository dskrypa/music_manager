"""
:author: Doug Skrypa
"""

import logging
import re
from fnmatch import translate as fnmatch_to_regex_str

from ds_tools.core import Paths
from ds_tools.input import get_input
from ..files import iter_album_dirs, iter_music_files, TagException, iter_albums_or_files

__all__ = ['path_to_tag', 'update_tags_with_value', 'clean_tags', 'remove_tags']
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


def clean_tags(paths: Paths, dry_run=False, add_bpm=False):
    for album_dir in iter_album_dirs(paths):
        album_dir.remove_bad_tags(dry_run)
        album_dir.fix_song_tags(dry_run, add_bpm)


def remove_tags(paths: Paths, tag_ids, dry_run=False):
    for music_file in iter_music_files(paths):
        music_file.remove_tags(tag_ids, dry_run, logging.INFO)
