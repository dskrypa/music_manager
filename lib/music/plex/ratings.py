"""
Plex Track rating utilities

:author: Doug Skrypa
"""

import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Union, Iterable

from ..common.ratings import stars
from ..files.track.track import SongFile
from .server import LocalPlexServer
from .utils import parse_filters

__all__ = ['find_and_rate', 'sync_ratings', 'adjust_track_ratings']
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

    prefix = '[DRY RUN] Would update' if plex.dry_run else 'Updating'
    for obj in objects:
        if obj.userRating == rating:
            log.info(f'No changes necessary for {obj}')
        else:
            log.info(f"{prefix} {obj}'s rating => {stars(rating)}")
            if not plex.dry_run:
                obj.edit(**{'userRating.value': rating})


def sync_ratings(plex: LocalPlexServer, direction: str, path_filter: str = None, parallel: int = 4):
    """
    Sync the song ratings from this Plex server to the files

    :param plex: A :class:`LocalPlexServer`
    :param direction: ``from_files`` to sync from files to Plex, ``to_files`` to sync from Plex to files
    :param path_filter: String that file paths must contain to be sync'd
    :param parallel: Number of workers to use in parallel
    """
    RatingSynchronizer(plex, path_filter, parallel).sync(direction == 'from_files')


class RatingSynchronizer:
    def __init__(self, plex: LocalPlexServer, path_filter: str = None, parallel: int = 4):
        if plex.server_root is None:
            raise ValueError(f"The custom.server_path_root is missing from {plex._config_path} and wasn't provided")
        self.plex = plex
        self.dry_run = plex.dry_run
        self.path_filter = path_filter
        self.prefix = '[DRY RUN] Would update' if plex.dry_run else 'Updating'
        self.parallel = parallel

    def sync(self, to_plex: bool):
        kwargs = {'media__part__file__icontains': self.path_filter} if self.path_filter else {}
        if to_plex:
            func, tracks = self._sync_to_plex, self.plex.get_tracks(**kwargs)
        else:
            func, tracks = self._sync_to_file, self.plex.find_songs_by_rating_gte(1, **kwargs)

        if not tracks:
            log.warning(f'No tracks found with path_filter={self.path_filter!r}')

        with ThreadPoolExecutor(max_workers=self.parallel) as executor:
            futures = (executor.submit(func, track) for track in tracks)
            for future in as_completed(futures):
                future.result()

    def _sync_to_file(self, track):
        file = SongFile.for_plex_track(track, self.plex.server_root)
        file_stars = file.star_rating_10
        plex_stars = track.userRating
        if file_stars == plex_stars:
            log.log(9, f'Rating is already correct for {file}')
        else:
            log.info(f'{self.prefix} rating from {file_stars} to {plex_stars} for {file}')
            if not self.dry_run:
                file.star_rating_10 = plex_stars

    def _sync_to_plex(self, track):
        file = SongFile.for_plex_track(track, self.plex.server_root)
        if (file_stars := file.star_rating_10) is None:
            log.log(9, f'No rating is stored for {file}')
            return

        plex_stars = track.userRating
        if file_stars == plex_stars:
            log.log(9, f'Rating is already correct for {file}')
        else:
            log.info(f'{self.prefix} rating from {plex_stars} to {file_stars} for {file}')
            if not self.dry_run:
                track.edit(**{'userRating.value': file_stars})


def adjust_track_ratings(plex: LocalPlexServer, min_rating: int = 2, max_rating: int = 10, offset: int = -1):
    from ..common.ratings import stars
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
