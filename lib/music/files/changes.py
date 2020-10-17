"""
:author: Doug Skrypa
"""

from collections import defaultdict, Counter
from typing import TYPE_CHECKING, Mapping, Tuple, Any, Dict

from ds_tools.output import colored, uprint
from ds_tools.output.table import mono_width

if TYPE_CHECKING:
    from .album import AlbumDir
    from .track.track import SongFile

__all__ = ['count_tag_changes', 'print_tag_changes', 'get_common_changes']


def count_tag_changes(
    updates: Mapping['SongFile', Mapping[str, Any]], add_genre: bool = True
) -> Dict[str, Dict[Tuple[Any, Any], int]]:
    counts = defaultdict(Counter)
    for file, values in updates.items():
        for tag_name, new_val in values.items():
            if tag_name in ('disk', 'track'):
                orig = getattr(file, f'{tag_name}_num')
            else:
                orig = file.tag_text(tag_name, default=None)

            if add_genre and tag_name == 'genre':
                orig_vals = set(file.tag_genres)
                new_vals = {new_val} if isinstance(new_val, str) else set(new_val)
                if orig_vals.issuperset(new_vals):
                    continue
                else:
                    new_val = ';'.join(sorted(orig_vals.union(new_vals)))

            if isinstance(new_val, list):
                new_val = tuple(new_val)

            counts[tag_name][(orig, new_val)] += 1
    return counts


def print_tag_changes(obj, changes: Mapping[str, Tuple[Any, Any]], dry_run: bool, color=None):
    name_width = max(len(tag_name) for tag_name in changes) if changes else 0
    orig_width = max(max(len(r), mono_width(r)) for r in (repr(orig) for orig, _ in changes.values())) if changes else 0
    _fmt = '  - {{:<{}s}}{}{{:>{}s}}{}{{}}'

    if changes:
        uprint(colored('{} {} by changing...'.format('[DRY RUN] Would update' if dry_run else 'Updating', obj), color))
        for tag_name, (orig_val, new_val) in changes.items():
            if tag_name == 'title':
                bg, reset, w = 20, False, 20
            else:
                bg, reset, w = None, True, 14

            orig_repr = repr(orig_val)
            fmt = _fmt.format(
                name_width + w,
                colored(' from ', 15, bg, reset=reset),
                orig_width - (mono_width(orig_repr) - len(orig_repr)) + w,
                colored(' to ', 15, bg, reset=reset),
            )

            uprint(colored(
                fmt.format(
                    colored(tag_name, 14, bg, reset=reset),
                    colored(orig_repr, 11, bg, reset=reset),
                    colored(repr(new_val), 10, bg, reset=reset),
                ),
                bg_color=bg,
            ))
    else:
        prefix = '[DRY RUN] ' if dry_run else ''
        uprint(colored(f'{prefix}No changes necessary for {obj}', color))


def get_common_changes(
    album_dir: 'AlbumDir',
    updates: Mapping['SongFile', Mapping[str, Any]],
    show: bool = True,
    extra_newline: bool = False,
    dry_run: bool = False,
    add_genre: bool = True,
) -> Dict[str, Tuple[Any, Any]]:
    counts = count_tag_changes(updates, add_genre)
    # noinspection PyUnboundLocalVariable
    common_changes = {
        tag_name: val_tup for tag_name, tag_counts in sorted(counts.items())
        if len(tag_counts) == 1 and (val_tup := next(iter(tag_counts))) and val_tup[0] != val_tup[1]
    }
    if show and common_changes:
        if extra_newline:
            print()
        print_tag_changes(album_dir, common_changes, dry_run, 10)
        print()

    return common_changes
