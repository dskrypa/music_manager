"""
:author: Doug Skrypa
"""

import logging
from collections import defaultdict, Counter

from mutagen.id3 import ID3

from ds_tools.core import Paths
from ds_tools.core.patterns import FnMatcher
from ds_tools.output import uprint, Table, SimpleColumn, TableBar
from ..constants import tag_name_map
from ..files import iter_album_dirs, iter_music_files, tag_repr, AlbumDir

__all__ = [
    'print_track_info', 'table_song_tags', 'table_unique_tag_values', 'table_tag_type_counts', 'print_processed_info'
]
log = logging.getLogger(__name__)


def print_processed_info(paths: Paths, expand=0, only_errors=False):
    for album_dir in iter_album_dirs(paths):
        if not only_errors:
            uprint(f'- Directory: {album_dir}')
        _print_one_or_set(album_dir, 'names', 'Album', only_errors=only_errors)
        single_artist = len(album_dir.all_artists) == 1
        if not expand or single_artist:
            _print_one_or_set(album_dir, 'artists', 'Artist', lambda a: a.artist_str(), only_errors)
        if expand:
            print_tracks(album_dir, expand)


def print_tracks(album_dir: AlbumDir, expand=0):
    single_artist = len(album_dir.all_artists) == 1
    uprint(f'    - Tracks ({len(album_dir)}):')
    for track in album_dir.songs:
        uprint(f'      - {track.path.name}:')
        uprint(f'         - Title       : {track.tag_title!r}')
        if not single_artist or expand > 1:
            uprint(f'         - Artist      : {track.tag_artist!r} =>')
            _print_one_or_set(track, 'artists', 'Processed', lambda a: repr(a.artist_str()), indent=11)
            uprint(f'         - Album Artist: {track.tag_album_artist!r} =>')
            _print_one_or_set(track, 'album_artists', 'Processed', lambda a: repr(a.artist_str()), indent=11)


def _print_one_or_set(obj, attr: str, singular: str, str_fn=str, only_errors=False, indent=4):
    prefix = ' ' * indent
    plural = singular if singular == 'Processed' else singular + 's'
    try:
        objs = getattr(obj, attr)
    except Exception as e:
        if only_errors:
            uprint(f'- Directory: {obj}')
        log.error(f'{prefix}{plural:12s}: {e}', extra={'color': 'red'}, exc_info=True)
    else:
        if not only_errors:
            if len(objs) == 1:
                uprint(f'{prefix}{singular:12s}: {str_fn(next(iter(objs)))}')
            else:
                text = f'{plural} ({len(objs)})'
                uprint(f'{prefix}{text:12s}:')
                for obj in objs:
                    uprint(f'{prefix}  - {str_fn(obj)} ')


def print_track_info(paths: Paths, tags=None, meta_only=False, trim=True):
    tags = {tag.upper() for tag in tags} if tags else None
    suffix = '' if meta_only else ':'
    for i, music_file in enumerate(iter_music_files(paths)):
        if i and not meta_only:
            print()

        uprint(f'{music_file.filename} [{music_file.length_str}] ({music_file.tag_version}){suffix}')
        if not meta_only:
            tbl = Table(SimpleColumn('Tag'), SimpleColumn('Tag Name'), SimpleColumn('Value'), update_width=True)
            rows = []
            for tag, val in sorted(music_file.tags.items()):
                if trim and len(tag) > 4:
                    tag = tag[:4]

                if not tags or (tag in tags):
                    rows.append({'Tag': tag, 'Tag Name': tag_name_map.get(tag, '[unknown]'), 'Value': tag_repr(val)})
            if rows:
                tbl.print_rows(rows)


def table_song_tags(paths: Paths, include_tags=None):
    rows = [{'path': '[Tag Description]'}, TableBar()]
    tags = set()
    values = defaultdict(Counter)
    for music_file in iter_music_files(paths):
        row = defaultdict(str, path=music_file.rel_path)
        for tag, val in sorted(music_file.tags.items()):
            tag = ':'.join(tag.split(':')[:2])
            if not include_tags or tag in include_tags:
                tags.add(tag)
                row[tag] = val_repr = tag_repr(val)
                values[tag][val_repr] += 1
        rows.append(row)

    rows[0].update({tag: tag_name_map.get(tag[:4], '[unknown]') for tag in tags})

    # noinspection PyUnboundLocalVariable
    if (artists := values['TPE1']) and (alb_artists := values['TPE2']) and (artists == alb_artists):
        tags.add('TPE1/2')
        rows[0]['TPE1/2'] = '(Album) Artist'
        for key in ('TPE1', 'TPE2'):
            tags.remove(key)
            del rows[0][key]

        for row in rows[2:]:
            del row['TPE2']
            row['TPE1/2'] = row.pop('TPE1')

    tbl = Table(SimpleColumn('path'), *(SimpleColumn(tag) for tag in sorted(tags)), update_width=True)
    tbl.print_rows(rows)


def table_unique_tag_values(paths: Paths, tag_ids):
    matches = FnMatcher(tag_ids, ignore_case=True).matches
    unique_vals = defaultdict(Counter)
    for music_file in iter_music_files(paths):
        for tag, name, val in music_file.iter_clean_tags():
            if matches((tag, name)):
                unique_vals[tag][str(val)] += 1

    tbl = Table(
        SimpleColumn('Tag'), SimpleColumn('Tag Name'), SimpleColumn('Count', align='>', ftype=',d'),
        SimpleColumn('Value'), update_width=True
    )
    rows = [
        {'Tag': tag, 'Tag Name': tag_name_map.get(tag, '[unknown]'), 'Count': count, 'Value': tag_repr(val)}
        for tag, val_counter in unique_vals.items() for val, count in val_counter.items()
    ]
    tbl.print_rows(rows)


def table_tag_type_counts(paths: Paths):
    total_tags, unique_tags, id3_versions = Counter(), Counter(), Counter()
    unique_values = defaultdict(Counter)
    files = 0
    for music_file in iter_music_files(paths):
        files += 1
        tag_set = set()
        for tag, name, val in music_file.iter_clean_tags():
            tag_set.add(tag)
            total_tags[tag] += 1
            unique_values[tag][str(val)] += 1

        unique_tags.update(tag_set)
        if isinstance(music_file.tags, ID3):
            id3_versions[music_file.tag_version] += 1

    tag_rows = [{
        'Tag': tag, 'Tag Name': tag_name_map.get(tag, '[unknown]'), 'Total': total_tags[tag], 'Files': unique_tags[tag],
        'Files %': unique_tags[tag] / files, 'Per File (overall)': total_tags[tag] / files,
        'Per File (with tag)': total_tags[tag] / unique_tags[tag], 'Unique Values': len(unique_values[tag])
        } for tag in unique_tags
    ]
    tbl = Table(
        SimpleColumn('Tag'), SimpleColumn('Tag Name'), SimpleColumn('Total', align='>', ftype=',d'),
        SimpleColumn('Files', align='>', ftype=',d'), SimpleColumn('Files %', align='>', ftype=',.0%'),
        SimpleColumn('Per File (overall)', align='>', ftype=',.2f'),
        SimpleColumn('Per File (with tag)', align='>', ftype=',.2f'),
        SimpleColumn('Unique Values', align='>', ftype=',d'), update_width=True, sort_by='Tag'
    )
    tbl.print_rows(tag_rows)

    print()
    tbl = Table(SimpleColumn('Version'), SimpleColumn('Count'), update_width=True, sort_by='Version')
    tbl.print_rows([{'Version': ver, 'Count': count} for ver, count in id3_versions.items()])
