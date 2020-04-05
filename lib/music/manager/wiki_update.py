"""
:author: Doug Skrypa
"""

import logging
from collections import defaultdict, Counter
from functools import partial
from pathlib import Path
from typing import Union, Optional, Dict, Any

from ds_tools.core import Paths, get_input, parse_with_func
from ds_tools.output import colored
from ..files import iter_album_dirs, AlbumDir, SafePath
from ..files.track import SongFile, print_tag_changes
from ..wiki import Track, Singer, DiscographyEntry, DiscographyEntryEdition, DiscographyEntryPart
from ..wiki.parsing.utils import LANG_ABBREV_MAP
from .enums import CollabMode as CM

__all__ = ['update_tracks']
log = logging.getLogger(__name__)
DiscoObj = Union[DiscographyEntry, DiscographyEntryEdition, DiscographyEntryPart]
ARTIST_TYPE_DIRS = SafePath('{artist}/{type_dir}')
TRACK_NAME_FORMAT = SafePath('{num}. {track}.{ext}')


def update_tracks(
        paths: Paths, dry_run=False, soloist=False, hide_edition=False, collab_mode: Union[CM, str] = CM.ARTIST,
        url: Optional[str] = None, add_bpm=False, dest_base_dir: Union[Path, str, None] = None
):
    if not isinstance(collab_mode, CM):
        collab_mode = CM(collab_mode)
    if dest_base_dir is not None and not isinstance(dest_base_dir, Path):
        dest_base_dir = Path(dest_base_dir).expanduser().resolve()

    if url:
        album_dirs = list(iter_album_dirs(paths))
        if len(album_dirs) > 1:
            raise ValueError('When a wiki URL is provided, only one album can be processed at a time')

        entry = DiscographyEntry.from_url(url)
        return _update_album_from_disco_entry(
            album_dirs[0], entry, dry_run, soloist, hide_edition, collab_mode, add_bpm, dest_base_dir
        )
    else:
        raise NotImplementedError('Automatic matching is not yet implemented')


def _update_album_from_disco_entry(
        album_dir: AlbumDir, entry: DiscoObj, dry_run=False, soloist=False, hide_edition=False,
        collab_mode: CM = CM.ARTIST, add_bpm=False, dest_base_dir: Optional[Path] = None
):
    album_dir.remove_bad_tags(dry_run)
    album_dir.fix_song_tags(dry_run, add_bpm)

    disco_part = _get_disco_part(entry)                                         # type: DiscographyEntryPart
    ft_iter = zip(sorted(album_dir.songs, key=lambda sf: sf.track_num), disco_part.tracks)
    file_track_map = {file: track for file, track in ft_iter}                   # type: Dict[SongFile, Track]

    updates = {}                                                                # type: Dict[SongFile, Dict[str, Any]]
    counts = defaultdict(Counter)
    for file, track in file_track_map.items():
        updates[file] = values = _get_update_values(track, soloist, hide_edition, collab_mode)
        for tag_name, new_val in values.items():
            if tag_name in ('disk', 'track'):
                orig = getattr(file, f'{tag_name}_num')
            else:
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

    prefix = '[DRY RUN] Would rename' if dry_run else 'Renaming'
    for file, values in updates.items():
        if file.tag_type == 'mp4':
            values['track'] = (values['track'], len(file_track_map))    # TODO: Handle incomplete file set
            values['disk'] = (values['disk'], values['disk'])           # TODO: get actual disk count
        file.update_tags(values, dry_run, no_log=common_changes)

        track = file_track_map[file]
        filename = TRACK_NAME_FORMAT(track=track.full_name(True), ext=file.ext, num=track.num)
        if file.path.name != filename:
            rel_path = Path(file.rel_path)
            log.info(f'{prefix} {rel_path.parent}/{colored(rel_path.name, 11)} -> {colored(filename, 10)}')
            if not dry_run:
                file.rename(file.path.with_name(filename))

    if dest_base_dir:
        edition = disco_part.edition
        rel_dir_fmt = ARTIST_TYPE_DIRS + _album_format(edition.date, edition.type.numbered and edition.entry.number)
        expected_rel_dir = rel_dir_fmt(
            artist=edition.artist.name.english, type_dir=edition.type.directory, album_num=edition.numbered_type,
            album=disco_part.full_name(hide_edition), date=edition.date
        )
        expected_dir = dest_base_dir.joinpath(expected_rel_dir)
        if expected_dir != album_dir.path:
            prefix = '[DRY RUN] Would move' if dry_run else 'Moving'
            log.info(f'{prefix} {album_dir} -> {expected_dir}')
            if not dry_run:
                album_dir.move(expected_dir)
                # TODO: cleanup empty original dir(s)
        else:
            log.log(19, f'Album {album_dir} is already in expected dir: {expected_dir}')


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
    values['album'] = album_part.full_name(hide_edition)

    lang = album_edition.lang
    lang = LANG_ABBREV_MAP.get(lang.lower()) if lang else None
    if lang in ('Chinese', 'Japanese', 'Korean', 'Mandarin'):
        values['genre'] = f'{lang[0]}-pop'

    return values


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


def _album_format(date, num):
    if date and num:
        return SafePath('[{date}] {album} [{album_num}]')
    elif date:
        return SafePath('[{date}] {album}')
    elif num:
        return SafePath('{album} [{album_num}]')
    else:
        return SafePath('{album}')
