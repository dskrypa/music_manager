"""
Plex Track rating utilities

:author: Doug Skrypa
"""

import logging
from collections import defaultdict
from typing import Union, Iterable

from ..common.ratings import stars
from ..files.track.track import SongFile
from .server import LocalPlexServer
from .utils import parse_filters

__all__ = ['find_and_rate', 'sync_ratings', 'sync_ratings_to_files', 'sync_ratings_from_files', 'adjust_track_ratings']
log = logging.getLogger(__name__)


def find_and_rate(
    plex: LocalPlexServer,
    rating: int,
    obj_type: str,
    title: Union[str, Iterable[str]],
    filters: Union[dict[str, str], str],
    escape: str,
    allow_inst: bool,
):
    if rating < 0 or rating > 10:
        raise ValueError(f'Invalid {rating=} - must be between 0 and 10')
    obj_type, kwargs = parse_filters(obj_type, title, filters, escape, allow_inst)
    if len(kwargs) == 1:
        raise ValueError('At least one identifier is required')
    objects = plex.find_objects(obj_type, **kwargs)
    if not objects:
        log.warning('No results.')
    else:
        prefix = '[DRY RUN] Would update' if plex.dry_run else 'Updating'
        for obj in objects:
            if obj.userRating == rating:
                log.info(f'No changes necessary for {obj}')
            else:
                log.info(f'{prefix} {obj}\'s rating => {stars(rating)}')
                if not plex.dry_run:
                    obj.edit(**{'userRating.value': rating})


def sync_ratings(plex: LocalPlexServer, direction: str, path_filter: str = None):
    if direction == 'to_files':
        sync_ratings_to_files(plex, path_filter)
    elif direction == 'from_files':
        sync_ratings_from_files(plex, path_filter)
    else:
        raise ValueError(f'Invalid rating sync {direction=}')


def sync_ratings_to_files(plex: LocalPlexServer, path_filter: str = None):
    """
    Sync the song ratings from this Plex server to the files

    :param plex: A :class:`LocalPlexServer`
    :param path_filter: String that file paths must contain to be sync'd
    """
    if plex.server_root is None:
        raise ValueError(f'The custom.server_path_root is missing from {plex._config_path} and wasn\'t provided')
    prefix = '[DRY RUN] Would update' if plex.dry_run else 'Updating'
    kwargs = {'media__part__file__icontains': path_filter} if path_filter else {}

    for track in plex.find_songs_by_rating_gte(1, **kwargs):
        file = SongFile.for_plex_track(track, plex.server_root)
        file_stars = file.star_rating_10
        plex_stars = track.userRating
        if file_stars == plex_stars:
            log.log(9, 'Rating is already correct for {}'.format(file))
        else:
            log.info('{} rating from {} to {} for {}'.format(prefix, file_stars, plex_stars, file))
            if not plex.dry_run:
                file.star_rating_10 = plex_stars


def sync_ratings_from_files(plex: LocalPlexServer, path_filter: str = None):
    """
    Sync the song ratings on this Plex server with the ratings in the files

    :param plex: A :class:`LocalPlexServer`
    :param path_filter: String that file paths must contain to be sync'd
    """
    if plex.server_root is None:
        raise ValueError(f'The custom.server_path_root is missing from {plex._config_path} and wasn\'t provided')
    prefix = '[DRY RUN] Would update' if plex.dry_run else 'Updating'
    kwargs = {'media__part__file__icontains': path_filter} if path_filter else {}
    for track in plex.get_tracks(**kwargs):
        file = SongFile.for_plex_track(track, plex.server_root)
        file_stars = file.star_rating_10
        if file_stars is not None:
            plex_stars = track.userRating
            if file_stars == plex_stars:
                log.log(9, 'Rating is already correct for {}'.format(file))
            else:
                log.info('{} rating from {} to {} for {}'.format(prefix, plex_stars, file_stars, file))
                if not plex.dry_run:
                    track.edit(**{'userRating.value': file_stars})


def adjust_track_ratings(plex: LocalPlexServer, min_rating: int = 2, max_rating: int = 10, offset: int = -1):
    from ..common.ratings import stars
    prefix = '[DRY RUN] Would update' if plex.dry_run else 'Updating'
    for obj in plex.get_tracks(userRating__gte=min_rating, userRating__lte=max_rating):
        rating = obj.userRating + offset
        log.info(f'{prefix} {obj}\'s rating => {stars(rating)}')
        if not plex.dry_run:
            obj.edit(**{'userRating.value': rating})


def find_dupe_ratings(plex: LocalPlexServer):
    rating_artist_title_map = defaultdict(lambda: defaultdict(lambda: defaultdict(set)))
    for track in plex.query('track', userRating__gte=1).results():
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
