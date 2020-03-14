"""
:author: Doug Skrypa
"""

import logging
import re
from fnmatch import translate as fnmatch_to_regex_str

from mutagen.id3 import ID3

from ds_tools.core.input import get_input
from .exceptions import TagException
from .utils import iter_music_files

__all__ = ['path_to_tag', 'update_tags']
log = logging.getLogger(__name__)


def update_tags(paths, tag_ids, value, replace_pats, partial, dry_run):
    patterns = [re.compile(fnmatch_to_regex_str(pat)[4:-3]) for pat in replace_pats] if replace_pats else []
    if partial and not patterns:
        raise ValueError('When using --partial/-p, --replace/-r must also be specified')

    for music_file in iter_music_files(paths):
        if not isinstance(music_file.tags, ID3):
            log.info('Skipping non-MP3: {}'.format(music_file.filename))
            continue

        music_file.update_tags_with_value(tag_ids, value, patterns=patterns, partial=partial, dry_run=dry_run)


def path_to_tag(path, dry_run=False, skip_prompt=False, title=False):
    """
    Update tags based on the path to each file

    :param str path: A directory that contains directories that contain music files
    :param bool dry_run: Print the actions that would be taken instead of taking them
    :param bool skip_prompt: Skip the prompt asking if a given file should be updated
    :param bool title: Update title based on filename
    """
    prefix = '[DRY RUN] Would update' if dry_run else 'Update'
    for music_file in iter_music_files(path):
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
                music_file.set_title(filename)
                music_file.save()
        else:
            log.log(19, f'Skipping file with already correct title: {music_file.filename}')
