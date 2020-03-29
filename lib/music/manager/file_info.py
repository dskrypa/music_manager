"""
:author: Doug Skrypa
"""

import logging
from collections import defaultdict, Counter

from mutagen.id3 import ID3

from ds_tools.core.patterns import FnMatcher
from ds_tools.output import uprint, Table, SimpleColumn, TableBar
from ..constants import tag_name_map
from ..files.track import tag_repr
from ..files.utils import iter_music_files

__all__ = ['print_track_info', 'table_song_tags', 'table_unique_tag_values', 'table_tag_type_counts']
log = logging.getLogger(__name__)


def print_track_info(paths, tags=None, meta_only=False, trim=True):
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


def table_song_tags(paths, include_tags=None):
    rows = [{'path': '[Tag Description]'}, TableBar()]
    tags = set()
    for music_file in iter_music_files(paths):
        row = defaultdict(str, path=music_file.filename)
        for tag, val in sorted(music_file.tags.items()):
            tag = ':'.join(tag.split(':')[:2])
            if not include_tags or tag in include_tags:
                tags.add(tag)
                row[tag] = tag_repr(val, 10, 5) if tag.startswith('APIC') else tag_repr(val)
        rows.append(row)

    rows[0].update({tag: tag_name_map.get(tag[:4], '[unknown]') for tag in tags})
    tbl = Table(SimpleColumn('path'), *(SimpleColumn(tag) for tag in sorted(tags)), update_width=True)
    tbl.print_rows(rows)


def table_unique_tag_values(paths, tag_ids):
    matcher = FnMatcher(tag_ids, ignore_case=True)
    unique_vals = defaultdict(Counter)
    for music_file in iter_music_files(paths):
        for tag, val in music_file.iter_clean_tags():
            if matcher.match(tag):
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


def table_tag_type_counts(paths):
    total_tags, unique_tags, id3_versions = Counter(), Counter(), Counter()
    unique_values = defaultdict(Counter)
    files = 0
    for music_file in iter_music_files(paths):
        files += 1
        tag_set = set()
        for tag, val in music_file.iter_clean_tags():
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
