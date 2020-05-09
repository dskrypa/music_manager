"""
:author: Doug Skrypa
"""

import logging
from pathlib import Path
from typing import Union, Optional, Dict, Any, Tuple

from ds_tools.core import Paths
from ds_tools.input import choose_item
from ds_tools.output import colored
from ..files import iter_album_dirs, AlbumDir, SafePath, SongFile, get_common_changes
from ..wiki import Track, Singer, DiscographyEntry, DiscographyEntryPart
from ..wiki.parsing.utils import LANG_ABBREV_MAP
from .enums import CollabMode as CM
from .wiki_match import find_album
from .wiki_utils import get_disco_part, DiscoObj

__all__ = ['update_tracks']
log = logging.getLogger(__name__)
ARTIST_TYPE_DIRS = SafePath('{artist}/{type_dir}')
SOLO_DIR_FORMAT = SafePath('{artist}/Solo/{singer}')
TRACK_NAME_FORMAT = SafePath('{num:02d}. {track}.{ext}')
TrackUpdates = Dict[SongFile, Dict[str, Any]]
UpdateCounts = Dict[str, Dict[Tuple[Any, Any], int]]


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
        _update_album_from_disco_entry(
            album_dirs[0], entry, dry_run, soloist, hide_edition, collab_mode, add_bpm, dest_base_dir
        )
    else:
        for album_dir in iter_album_dirs(paths):
            try:
                album = find_album(album_dir)
            except Exception as e:
                if isinstance(e, ValueError) and e.args[0] == 'No candidates found':
                    log.warning(f'No match found for {album_dir} ({album_dir.name})', extra={'color': 9})
                else:
                    log.error(f'Error finding an album match for {album_dir}: {e}', extra={'color': 9})
                    log.debug(f'Error finding an album match for {album_dir}:', exc_info=True)
            else:
                log.info(f'Matched {album_dir} to {album}')
                _update_album_from_disco_entry(
                    album_dir, album, dry_run, soloist, hide_edition, collab_mode, add_bpm, dest_base_dir
                )


def _update_album_from_disco_entry(
        album_dir: AlbumDir, entry: DiscoObj, dry_run=False, soloist=False, hide_edition=False,
        collab_mode: CM = CM.ARTIST, add_bpm=False, dest_base_dir: Optional[Path] = None
):
    album_dir.remove_bad_tags(dry_run)
    album_dir.fix_song_tags(dry_run, add_bpm)

    disco_part = get_disco_part(entry)                                          # type: DiscographyEntryPart
    ft_iter = zip(sorted(album_dir.songs, key=lambda sf: sf.track_num), disco_part.tracks)
    file_track_map = {file: track for file, track in ft_iter}                   # type: Dict[SongFile, Track]

    edition = disco_part.edition
    alb_artist = edition.artist
    if isinstance(alb_artist, Singer) and alb_artist.groups and not soloist:
        alb_artist = choose_item(alb_artist.groups, 'group', before=f'Found multiple groups for {alb_artist}')

    updates = {
        file: _get_update_values(track, alb_artist, soloist, hide_edition, collab_mode)
        for file, track in file_track_map.items()
    }
    _apply_track_updates(album_dir, file_track_map, updates, dry_run)
    _move_album_dir(album_dir, disco_part, dest_base_dir, soloist, alb_artist, hide_edition, dry_run)


def _apply_track_updates(album_dir: AlbumDir, file_track_map: Dict[SongFile, Track], updates: TrackUpdates, dry_run):
    common_changes = get_common_changes(album_dir, updates, extra_newline=True)
    prefix = '[DRY RUN] Would rename' if dry_run else 'Renaming'
    for file, values in updates.items():
        if file.tag_type == 'mp4':
            values['track'] = (values['track'], len(file_track_map))    # TODO: Handle incomplete file set
            values['disk'] = (values['disk'], values['disk'])           # TODO: get actual disk count
        file.update_tags(values, dry_run, no_log=common_changes)

        track = file_track_map[file]
        log.debug(f'Matched {file} to {track.name.full_repr()}')
        filename = TRACK_NAME_FORMAT(track=track.full_name(True), ext=file.ext, num=track.num)
        if file.path.name != filename:
            rel_path = Path(file.rel_path)
            log.info(f'{prefix} {rel_path.parent}/{colored(rel_path.name, 11)} -> {colored(filename, 10)}')
            if not dry_run:
                file.rename(file.path.with_name(filename))


def _move_album_dir(
        album_dir: AlbumDir, disco_part: DiscographyEntryPart, dest_base_dir: Optional[Path], soloist, alb_artist,
        hide_edition, dry_run
):
    edition = disco_part.edition
    artist = edition.artist
    alb_artist_name = artist.name.english
    rel_dir_fmt = _album_format(edition.date, edition.type.numbered and edition.entry.number)
    if dest_base_dir is None:
        dest_base_dir = album_dir.path.parent
    else:
        if isinstance(artist, Singer) and artist.groups and not soloist:
            rel_dir_fmt = SOLO_DIR_FORMAT + rel_dir_fmt
            alb_artist_name = alb_artist.name.english
        else:
            rel_dir_fmt = ARTIST_TYPE_DIRS + rel_dir_fmt

    expected_rel_dir = rel_dir_fmt(
        artist=alb_artist_name, type_dir=edition.type.directory, album_num=edition.numbered_type,
        album=disco_part.full_name(hide_edition), date=edition.date, singer=artist.name.english
    )
    expected_dir = dest_base_dir.joinpath(expected_rel_dir)
    if expected_dir != album_dir.path:
        prefix = '[DRY RUN] Would move' if dry_run else 'Moving'
        log.info(f'{prefix} {album_dir} -> {expected_dir}')
        if not dry_run:
            orig_parent_path = album_dir.path.parent
            album_dir.move(expected_dir)
            for path in (orig_parent_path, orig_parent_path.parent):
                log.log(19, f'Checking directory: {path}')
                if path.exists() and next(path.iterdir(), None) is None:
                    log.log(19, f'Removing empty directory: {path}')
                    path.rmdir()
    else:
        log.log(19, f'Album {album_dir} is already in the expected dir: {expected_dir}')


def _get_update_values(
        track: Track, alb_artist, soloist=False, hide_edition=False, collab_mode: CM = CM.ARTIST
) -> Dict[str, Any]:
    values = {}
    album_part = track.album_part
    album_edition = album_part.edition

    artist = album_edition.artist
    if isinstance(artist, Singer) and artist.groups and not soloist:
        group_name = str(alb_artist.name)
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


def _album_format(date, num):
    if date and num:
        return SafePath('[{date}] {album} [{album_num}]')
    elif date:
        return SafePath('[{date}] {album}')
    elif num:
        return SafePath('{album} [{album_num}]')
    else:
        return SafePath('{album}')
