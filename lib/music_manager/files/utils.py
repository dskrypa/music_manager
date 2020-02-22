"""
:author: Doug Skrypa
"""

import logging
import os
import pickle
from pathlib import Path

from .track.track import SongFile

__all__ = ['load_tags', 'iter_categorized_music_files', 'iter_music_albums', 'iter_music_files', 'FakeMusicFile']
log = logging.getLogger(__name__)

NON_MUSIC_EXTS = {'jpg', 'jpeg', 'png', 'jfif', 'part', 'pdf', 'zip'}


def iter_categorized_music_files(paths):
    if isinstance(paths, str):
        paths = [paths]

    for path in paths:
        path = os.path.abspath(os.path.expanduser(path))
        if os.path.isdir(path):
            if path.endswith(('/', '\\')):
                path = path[:-1]
            for root, dirs, files in os.walk(path):
                if files and not dirs:
                    alb_root, alb_dir = os.path.split(root)
                    cat_root, cat_dir = os.path.split(alb_root)
                    art_root, art_dir = os.path.split(cat_root)
                    yield art_root, art_dir, cat_dir, alb_dir, _iter_music_files((os.path.join(root, f) for f in files))
        elif os.path.isfile(path):
            alb_root, alb_dir = os.path.split(os.path.dirname(path))
            cat_root, cat_dir = os.path.split(alb_root)
            art_root, art_dir = os.path.split(cat_root)
            yield art_root, art_dir, cat_dir, alb_dir, _iter_music_files(path)


def iter_music_albums(paths):
    if isinstance(paths, str):
        paths = [paths]

    for path in paths:
        path = os.path.abspath(os.path.expanduser(path))
        if os.path.isdir(path):
            if path.endswith(('/', '\\')):
                path = path[:-1]
            for root, dirs, files in os.walk(path):
                if files and not dirs:
                    alb_root, alb_dir = os.path.split(root)
                    yield alb_root, alb_dir, _iter_music_files((os.path.join(root, f) for f in files))
        elif os.path.isfile(path):
            alb_root, alb_dir = os.path.split(os.path.dirname(path))
            yield alb_root, alb_dir, _iter_music_files(path)


def iter_music_files(paths, include_backups=False):
    if isinstance(paths, (str, Path)):
        paths = [paths]

    for path in paths:
        path = os.path.abspath(os.path.expanduser(path))
        if os.path.isdir(path):
            if path.endswith(('/', '\\')):
                path = path[:-1]
            for root, dirs, files in os.walk(path):
                yield from _iter_music_files((os.path.join(root, f) for f in files), include_backups)
        elif os.path.isfile(path):
            yield from _iter_music_files(path, include_backups)


def _iter_music_files(_path, include_backups=False):
    if isinstance(_path, str):
        _path = Path(_path).expanduser().resolve()
        paths = [p.as_posix() for p in _path.iterdir()] if _path.is_dir() else [_path.as_posix()]
    else:
        paths = _path

    for file_path in paths:
        music_file = SongFile(file_path)
        if music_file:
            yield music_file
        else:
            if include_backups and (os.path.splitext(file_path)[1][1:] not in NON_MUSIC_EXTS):
                found_backup = False
                for sha256sum, tags in load_tags(file_path).items():
                    found_backup = True
                    yield FakeMusicFile(sha256sum, tags)
                if not found_backup and not file_path.endswith('.jpg'):
                    log.debug('Not a music file: {}'.format(file_path))
            else:
                if not file_path.endswith('.jpg'):
                    log.debug('Not a music file: {}'.format(file_path))


class FakeMusicFile:
    def __init__(self, sha256sum, tags):
        self.filename = sha256sum
        self.tags = tags

    def tagless_sha256sum(self):
        return self.filename


def load_tags(paths):
    if isinstance(paths, str):
        paths = [paths]

    tag_info = {}
    for path in paths:
        if os.path.isdir(path):
            for root, dirs, files in os.walk(path):     # dirs can be ignored because walk will step through them -
                for f in files:                         #  they will be part of root on subsequent iterations
                    _load_tags(tag_info, os.path.join(root, f))
        elif os.path.isfile(path):
            _load_tags(tag_info, path)
        else:
            log.error('Invalid path: {}'.format(path))

    # tbl = Table(
    #     SimpleColumn('Hash'), SimpleColumn('Tag'), SimpleColumn('Tag Name'), SimpleColumn('Value'), update_width=True
    # )
    # rows = []
    # for sha256sum, tags in tag_info.items():
    #     for tag, val in tags.items():
    #         tag = tag[:4]
    #         rows.append({
    #             'Hash': sha256sum, 'Tag': tag, 'Value': tag_repr(val), 'Tag Name': tag_name_map.get(tag, '[unknown]')
    #         })
    # tbl.print_rows(rows)

    return tag_info


def _load_tags(tag_info, file_path):
    try:
        music_file = SongFile(file_path)
    except Exception as e:
        log.debug('Error loading {}: {}'.format(file_path, e))
        music_file = None

    if music_file:
        content_hash = music_file.tagless_sha256sum()
        log.debug('{}: {}'.format(music_file.filename, content_hash))
        tag_info[content_hash] = music_file.tags
    else:
        with open(file_path, 'rb') as f:
            try:
                tag_info.update(pickle.load(f))
            except Exception as e:
                log.debug('Unable to load tag info from file: {}'.format(file_path))
            else:
                log.debug('Loaded pickled tag info from {}'.format(file_path))
