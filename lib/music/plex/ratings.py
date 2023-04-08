"""
Plex Track rating utilities

:author: Doug Skrypa
"""

from __future__ import annotations

import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, date, timedelta
from threading import Event
from typing import TYPE_CHECKING, Union, Iterable

from ..common.ratings import stars
from ..files.track.track import SongFile
from ..files.paths import plex_track_path
from .config import config
from .server import LocalPlexServer
from .utils import parse_filters

if TYPE_CHECKING:
    from plexapi.audio import Track

__all__ = ['find_and_rate', 'RatingSynchronizer', 'adjust_track_ratings']
log = logging.getLogger(__name__)


def find_and_rate(
    plex: LocalPlexServer,
    rating: int,
    obj_type: str,
    title: Union[str, Iterable[str]],
    filters: Union[dict[str, str], str],
    escape: str,
    allow_inst: bool,
    pre_parsed: bool = False,
):
    if rating < 0 or rating > 10:
        raise ValueError(f'Invalid {rating=} - must be between 0 and 10')

    if pre_parsed:
        kwargs = filters
    else:
        obj_type, kwargs = parse_filters(obj_type, title, filters, escape, allow_inst)

    if len(kwargs) == 1:
        raise ValueError('At least one identifier is required')

    if not (objects := plex.find_objects(obj_type, **kwargs)):
        log.warning('No results.')
        return

    prefix = '[DRY RUN] Would update' if config.dry_run else 'Updating'
    for obj in objects:
        if obj.userRating == rating:
            log.info(f'No changes necessary for {obj}')
        else:
            log.info(f"{prefix} {obj}'s rating => {stars(rating)}")
            if not config.dry_run:
                obj.edit(**{'userRating.value': rating})


# region Sync Ratings


class RatingSynchronizer:
    """
    :param plex: A :class:`LocalPlexServer`
    :param path_filter: String that file paths must contain to be synced
    :param parallel: Number of workers to use in parallel
    :param mod_before: Only sync tracks with files modified before this time
    :param mod_after: Only sync tracks with files modified after this time
    """
    __slots__ = ('plex', 'dry_run', 'path_filter', 'prefix', 'parallel', 'interrupted', 'mod_before', 'mod_after')
    mod_before: datetime | date | None
    mod_after: datetime | date | None

    def __init__(
        self,
        plex: LocalPlexServer,
        path_filter: str = None,
        parallel: int = 4,
        *,
        mod_before: timedelta | datetime | date = None,
        mod_after: timedelta | datetime | date = None,
    ):
        if config.server_root is None:
            raise ValueError(f"The custom.server_path_root is missing from {config.path} and wasn't provided")
        self.plex = plex
        self.dry_run = plex.dry_run
        self.path_filter = path_filter
        self.prefix = '[DRY RUN] Would update' if plex.dry_run else 'Updating'
        self.parallel = parallel
        self.interrupted = Event()
        self.mod_before = _normalize_mod_time(mod_before)
        self.mod_after = _normalize_mod_time(mod_after)

    def sync(self, to_plex: bool):
        kwargs = {'mood__ne': 'Duplicate Rating'}
        if self.path_filter:
            kwargs['media__part__file__icontains'] = self.path_filter
        if to_plex:
            func, tracks = self._sync_to_plex, self.plex.get_tracks(**kwargs)
        else:
            func, tracks = self._sync_to_file, self.plex.find_songs_by_rating_gte(1, **kwargs)

        if not tracks:
            log.warning(f'No tracks found with path_filter={self.path_filter!r}')

        with ThreadPoolExecutor(max_workers=self.parallel) as executor:
            futures = (executor.submit(func, track) for track in tracks)
            try:
                for future in as_completed(futures):
                    future.result()
            except BaseException:  # inside the as_completed loop
                self.interrupted.set()
                executor.shutdown(cancel_futures=True)
                raise

    def _get_song_file(self, track: Track) -> SongFile | None:
        path = plex_track_path(track, config.server_root)
        mod_before, mod_after = self.mod_before, self.mod_after
        if mod_before or mod_after:
            modified = datetime.fromtimestamp(path.stat().st_mtime)
            if mod_before and modified > mod_before:
                log.log(9, f'Skipping {path.as_posix()} because modified={_dt_repr(modified)} > {_dt_repr(mod_before)}')
                return None
            elif mod_after and modified < mod_after:
                log.log(9, f'Skipping {path.as_posix()} because modified={_dt_repr(modified)} < {_dt_repr(mod_after)}')
                return None
        return SongFile(path)

    def _sync_to_file(self, track: Track):
        if self.interrupted.is_set() or not (file := self._get_song_file(track)):
            return

        file_stars = file.star_rating_10
        plex_stars = track.userRating
        if file_stars == plex_stars:
            log.log(9, f'Rating is already correct for {file}')
        else:
            log.info(f'{self.prefix} rating from {file_stars} to {plex_stars} for {file}')
            if not self.dry_run:
                file.star_rating_10 = plex_stars

    def _sync_to_plex(self, track: Track):
        if self.interrupted.is_set() or not (file := self._get_song_file(track)):
            return
        elif (file_stars := file.star_rating_10) is None:
            log.log(9, f'No rating is stored for {file}')
            return

        plex_stars = track.userRating
        if file_stars == plex_stars:
            log.log(9, f'Rating is already correct for {file}')
        else:
            log.info(f'{self.prefix} rating from {plex_stars} to {file_stars} for {file}')
            if not self.dry_run:
                track.edit(**{'userRating.value': file_stars})


def _dt_repr(dt: datetime) -> str:
    return dt.isoformat(' ', 'seconds')


def _normalize_mod_time(dt_or_delta: datetime | date | timedelta | None) -> datetime | date | None:
    if not dt_or_delta:
        return None
    elif isinstance(dt_or_delta, timedelta):
        return datetime.now() - dt_or_delta
    else:
        return dt_or_delta


# endregion


def adjust_track_ratings(plex: LocalPlexServer, min_rating: int = 2, max_rating: int = 10, offset: int = -1):
    from music.common.ratings import stars

    prefix = '[DRY RUN] Would update' if plex.dry_run else 'Updating'
    for track in plex.get_tracks(userRating__gte=min_rating, userRating__lte=max_rating):
        rating = track.userRating + offset
        log.info(f"{prefix} {track}'s rating => {stars(rating)}")
        if not plex.dry_run:
            track.edit(**{'userRating.value': rating})


def find_dupe_ratings(plex: LocalPlexServer):
    rating_artist_title_map = defaultdict(lambda: defaultdict(lambda: defaultdict(set)))
    for track in plex.query('track', userRating__gte=1, mood__ne='Duplicate Rating').results():
        rating_artist_title_map[track.userRating][track.grandparentTitle][track.title].add(track)

    duplicates = []
    for rating, artist_title_maps in rating_artist_title_map.items():
        for artist, title_maps in artist_title_maps.items():
            for title, title_tracks in title_maps.items():
                if len(title_tracks) > 1:
                    duplicates.append(title_tracks)
    return duplicates


def find_dupe_ratings_by_artist(plex: LocalPlexServer):
    dupes_by_artist = {}
    dupes = find_dupe_ratings(plex)
    for dupe in sorted(dupes, key=lambda g: next(iter(g)).grandparentTitle):
        artist = next(iter(dupe)).grandparentTitle
        dupes_by_artist.setdefault(artist, []).append(dupe)

    return dupes_by_artist


def print_dupe_ratings_by_artist(plex: LocalPlexServer):
    all_dupes = find_dupe_ratings_by_artist(plex)
    total = sum(map(len, all_dupes.values()))
    print(f'Found a total of {total} sets of duplicate track ratings across {len(all_dupes)} artists')
    for i, (artist, dupes) in enumerate(all_dupes.items()):
        if i:
            print()
        print(f'{artist}: {len(dupes)}')
        for dupe in dupes:
            print('    - {}'.format(', '.join(map(repr, dupe))))
