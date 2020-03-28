"""
:author: Doug Skrypa
"""

import logging
from collections import defaultdict, Counter
from functools import partial
from typing import Union, Optional, Dict, Any

from ds_tools.core import Paths, get_input, parse_with_func
from ..files import iter_album_dirs, AlbumDir
from ..files.track import SongFile, print_tag_changes
from ..text import combine_with_parens
from ..wiki import Track, Singer, DiscographyEntry, DiscographyEntryEdition, DiscographyEntryPart
from ..wiki.parsing.utils import LANG_ABBREV_MAP
from .enums import CollabMode as CM

__all__ = ['update_tracks']
log = logging.getLogger(__name__)
DiscoObj = Union[DiscographyEntry, DiscographyEntryEdition, DiscographyEntryPart]


def update_tracks(
        paths: Paths, dry_run=False, soloist=False, hide_edition=False, collab_mode: Union[CM, str] = CM.ARTIST,
        url: Optional[str] = None
):
    if not isinstance(collab_mode, CM):
        collab_mode = CM(collab_mode)

    if url:
        album_dirs = list(iter_album_dirs(paths))
        if len(album_dirs) > 1:
            raise ValueError('When a wiki URL is provided, only one album can be processed at a time')

        entry = DiscographyEntry.from_url(url)
        return _update_album_from_disco_entry(album_dirs[0], entry, dry_run, soloist, hide_edition, collab_mode)
    else:
        raise NotImplementedError('Automatic matching is not yet implemented')


def _update_album_from_disco_entry(
        album_dir: AlbumDir, entry: DiscoObj, dry_run=False, soloist=False, hide_edition=False,
        collab_mode: CM = CM.ARTIST
):
    album_dir.remove_bad_tags(dry_run)
    album_dir.fix_song_tags(dry_run)

    updates = {}
    counts = defaultdict(Counter)
    for file, track in zip(sorted(album_dir.songs, key=lambda sf: sf.track_num), _get_disco_part(entry).tracks):
        values = _get_update_values(track, soloist, hide_edition, collab_mode)
        updates[file] = values
        for tag_name, new_val in values.items():
            orig = file.tag_text(tag_name)
            counts[tag_name][(orig, new_val)] += 1

    # noinspection PyUnboundLocalVariable
    common_changes = {
        tag_name: val_tup for tag_name, tag_counts in sorted(counts.items())
        if len(tag_counts) == 1 and (val_tup := next(iter(tag_counts))) and val_tup[0] != val_tup[1]
    }
    if common_changes:
        print()
        print_tag_changes(album_dir, common_changes, 10)
        print()

    for file, values in updates.items():
        file.update_tags(values, dry_run, no_log=common_changes)

    # TODO: Move/rename files


def _get_update_values(track: Track, soloist=False, hide_edition=False, collab_mode: CM = CM.ARTIST) -> Dict[str, Any]:
    values = {}
    album_part = track.album_part
    album_edition = album_part.edition

    artist = album_edition.artist
    if isinstance(artist, Singer) and artist.groups and not soloist:
        group_name = str(artist.groups[0].name)
        values['album_artist'] = group_name
        values['artist'] = f'{artist.name} ({group_name})'
    else:
        values['artist'] = values['album_artist'] = str(artist.name)

    if collab_mode in (CM.ARTIST, CM.BOTH) and (collabs := track.collab_parts):
        # noinspection PyUnboundLocalVariable
        values['artist'] = '{} {}'.format(values['artist'], ' '.join(f'({part})' for part in collabs))

    values['title'] = track.full_name(collab_mode in (CM.TITLE, CM.BOTH))
    values['date'] = album_edition.date.strftime('%Y%m%d')
    values['track'] = track.num
    values['disk'] = album_part.disc

    lang = album_edition.lang
    lang = LANG_ABBREV_MAP.get(lang.lower()) if lang else None
    if lang in ('Chinese', 'Japanese', 'Korean', 'Mandarin'):
        values['genre'] = f'{lang[0]}-pop'

    album_name_parts = [album_edition.name, album_part.name]
    if not hide_edition:
        album_name_parts.append(album_edition.edition)
    values['album'] = combine_with_parens(list(filter(None, album_name_parts)))

    return values


def update_track(
        file: SongFile, track: Track, dry_run=False, soloist=False, hide_edition=False, collab_mode: CM = CM.ARTIST
):
    values = _get_update_values(track, soloist, hide_edition, collab_mode)
    file.update_tags(values, dry_run)
    return values['title']


def _get_disco_part(entry: DiscoObj) -> DiscographyEntryPart:
    if isinstance(entry, DiscographyEntry):
        entry = _get_choice(entry, entry.editions, 'edition')
    if isinstance(entry, DiscographyEntryEdition):
        entry = _get_choice(entry, entry.parts, 'part')
    if isinstance(entry, DiscographyEntryPart):
        return entry
    else:
        raise TypeError(f'Expected a DiscographyEntryPart, but {entry=} is a {type(entry).__name__}')


def _get_choice(source, values, name):
    if not values:
        raise ValueError(f'No {name}s found for {source}')
    elif len(values) > 1:
        log.info(f'Found multiple {name}s for {source}:')
        for i, value in enumerate(values):
            log.info(f'{i}: {value}')
        choice = get_input(f'Which {name} should be used [specify the number]?', parser=partial(parse_with_func, int))
        try:
            return values[choice]
        except IndexError as e:
            raise ValueError(f'Invalid {name} index - must be a value from 0 to {len(values)}') from e
    else:
        return next(iter(values))
