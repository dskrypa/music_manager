"""
:author: Doug Skrypa
"""

import logging
from collections import defaultdict
from itertools import chain
from operator import eq
from typing import TYPE_CHECKING, Collection, Iterator, Set

from plexapi.audio import Track

from ..files.track.track import SongFile
from ..text import Name
from .utils import _show_filters

if TYPE_CHECKING:
    from .server import LocalPlexServer, PlexObjTypes, PlexObj

__all__ = ['QueryResults', 'PlexQueryException', 'InvalidQueryFilter']
log = logging.getLogger(__name__)
AUDIO_TYPES = {'track', 'album', 'artist'}


class QueryResults:
    def __init__(self, server: 'LocalPlexServer', obj_type: 'PlexObjTypes', results: Collection['PlexObj']):
        self.server = server
        self._type = obj_type
        self._results = set(results) if not isinstance(results, set) else results                   # type: Set[PlexObj]

    def __repr__(self):
        return f'<{self.__class__.__name__}[{len(self._results):,d} {self._type}s]>'

    def results(self) -> Collection['PlexObj']:
        return self._results

    def __iter__(self) -> Iterator['PlexObj']:
        return iter(self._results)

    def __bool__(self):
        return bool(self._results)

    def __len__(self, other):
        return len(self._results)

    def __serializable__(self):
        return self._results

    def __validate(self, other, op):
        if not isinstance(other, QueryResults):
            raise TypeError(f'Unable to {op} results with type={other.__class__.__name__}')
        elif self._type != other._type:
            raise ValueError(f'Unable to {op} results for incompatible types ({self._type}, {other._type})')
        elif self.server != other.server:
            raise ValueError(f'Unable to {op} results from different servers ({self.server}, {other.server})')

    def __add__(self, other: 'QueryResults'):
        self.__validate(other, 'combine')
        return QueryResults(self.server, self._type, self._results.union(other._results))

    def __iadd__(self, other: 'QueryResults'):
        self.__validate(other, 'combine')
        self._results.update(other._results)
        return self

    def __sub__(self, other: 'QueryResults'):
        self.__validate(other, 'remove')
        return QueryResults(self.server, self._type, self._results - other._results)

    def __isub__(self, other: 'QueryResults'):
        self.__validate(other, 'remove')
        self._results -= other._results
        return self

    def artists(self, **kwargs) -> 'QueryResults':
        if self._type == 'artist':
            return self.filter(**kwargs)
        elif self._type == 'album':
            return self.server.query('artist', key__in={f'{obj.parentKey}/children' for obj in self}, **kwargs)
        elif self._type == 'track':
            return self.server.query('artist', key__in={f'{obj.grandparentKey}/children' for obj in self}, **kwargs)
        else:
            try:
                return QueryResults(self.server, 'artist', {obj.artist() for obj in self}).filter(**kwargs)
            except AttributeError as e:
                raise InvalidQueryFilter(str(e)) from e

    def albums(self, **kwargs) -> 'QueryResults':
        if self._type == 'album':
            return self.filter(**kwargs)
        elif self._type == 'artist':
            return self.server.query('album', parentKey__in={obj.key for obj in self}, **kwargs)
        elif self._type == 'track':
            return self.server.query('album', key__in={f'{obj.parentKey}/children' for obj in self}, **kwargs)
        else:
            try:
                return QueryResults(self.server, 'album', {obj.album() for obj in self}).filter(**kwargs)
            except AttributeError as e:
                raise InvalidQueryFilter(str(e)) from e

    def tracks(self, **kwargs) -> 'QueryResults':
        if self._type == 'track':
            return self.filter(**kwargs)
        elif self._type == 'artist':
            return self.server.query('track', grandparentKey__in={obj.key for obj in self}, **kwargs)
        elif self._type == 'album':
            return self.server.query('track', parentKey__in={obj.key for obj in self}, **kwargs)
        try:
            return QueryResults(self.server, 'track', {obj.tracks() for obj in self}).filter(**kwargs)
        except AttributeError as e:
            raise InvalidQueryFilter(str(e)) from e

    def with_rating(self, rating, op=eq) -> 'QueryResults':
        return QueryResults(self.server, self._type, {obj for obj in self if op(_get_rating(obj), rating)})

    def filter(self, **kwargs) -> 'QueryResults':
        if not kwargs:
            return self
        server = self.server
        if data := [obj._data for obj in self._results]:
            library_section_id = next(iter(self._results)).librarySectionID
            if self._type == 'track':
                results = set()
                for kwargs in server._updated_filters(self._type, kwargs):
                    _show_filters(kwargs)
                    results.update(server.music.findItems(data, **kwargs))
            else:
                kwargs = next(server._updated_filters(self._type, kwargs))
                _show_filters(kwargs)
                results = server.music.findItems(data, **kwargs)

            for obj in results:
                obj.librarySectionID = library_section_id
        else:
            log.debug(f'No results exist to filter')
            results = []

        return QueryResults(self.server, self._type, results)

    def unique(self, rated=True, fuzzy=True, latest=True, singles=False) -> 'QueryResults':
        """
        :param bool rated: When multiple versions of a track with a given name exist, and one of them has a rating,
          keep the one with the rating.  If False, ignore ratings.
        :param bool fuzzy: Process titles as :class:`Name<music.text.name.Name>` objects
        :param bool latest: When multiple versions of a track with a given name exist, keep the one that has the more
          recent release date
        :param bool singles: Before applying the `latest` filter, allow singles
        """
        if self._type != 'track':
            raise InvalidQueryFilter(f'unique() is only permitted for track results')

        artist_title_obj_map = defaultdict(dict)
        for track in self._results:                                     # type: Track
            artist = track.originalTitle if track.grandparentTitle == 'Various Artists' else track.grandparentTitle
            title_obj_map = artist_title_obj_map[artist]
            lc_title = track.title.lower()
            if existing := title_obj_map.get(lc_title):
                keep = _pick_uniq_track(existing, track, self.server, rated, latest, singles)
            else:
                keep = track

            title_obj_map[lc_title] = keep

        if fuzzy:
            name_from_enclosed = Name.from_enclosed
            results = set()
            for artist_key, title_obj_map in artist_title_obj_map.items():
                artist_uniq = {}
                for track in title_obj_map.values():
                    track_name = name_from_enclosed(track.title)
                    keep = track
                    if match := next(filter(track_name.matches, artist_uniq), None):
                        existing = artist_uniq.pop(match)
                        # log.debug(f'Found {match=!r} / {existing=} for {track_name=!r} / {track=}', extra={'color': 13})
                        keep = _pick_uniq_track(existing, track, self.server, rated, latest, singles)
                        keep_name = match if keep == existing else track_name
                    else:
                        # log.debug(f'{track_name=!r} / {track=} did not match any other tracks from {artist_key=!r}')
                        keep_name = track_name

                    artist_uniq[keep_name] = keep
                results.update(artist_uniq.values())
        else:
            results = set(chain.from_iterable(artist_title_obj_map.values()))

        return QueryResults(self.server, self._type, results)


def _pick_uniq_track(existing: Track, track: Track, server, rated, latest, singles) -> Track:
    if rated:
        if existing.userRating and not track.userRating:
            # log.debug(f'Keeping {existing=} instead of {track=} because of rating', extra={'color': 11})
            return existing
        elif not existing.userRating and track.userRating:
            # log.debug(f'Keeping {track=} instead of {existing=} because of rating', extra={'color': 11})
            return track
        elif latest and (latest_track := _get_latest(existing, track, server.server_root, singles)):
            # if latest_track == existing:
            #     log.debug(f'Keeping {existing=} instead of {track=} because of date', extra={'color': 11})
            # else:
            #     log.debug(f'Keeping {track=} instead of {existing=} because of date', extra={'color': 11})
            # noinspection PyUnboundLocalVariable
            return latest_track
        else:
            return min(existing, track)     # Ensure the chosen value is stable between runs
    elif latest and (latest_track := _get_latest(existing, track, server.server_root, singles)):
        # if latest_track == existing:
        #     log.debug(f'Keeping {existing=} instead of {track=} because of date', extra={'color': 11})
        # else:
        #     log.debug(f'Keeping {track=} instead of {existing=} because of date', extra={'color': 11})
        # noinspection PyUnboundLocalVariable
        return latest_track
    else:
        return min(existing, track)         # Ensure the chosen value is stable between runs


def _get_latest(a: Track, b: Track, server_root, singles):
    if singles:
        a_path = a.media[0].parts[0].file.lower()
        b_path = b.media[0].parts[0].file.lower()
        if '/singles/' in a_path and '/singles/' not in b_path:
            return b
        elif '/singles/' in b_path and '/singles/' not in a_path:
            return a

    a_file = SongFile.for_plex_track(a, server_root)
    b_file = SongFile.for_plex_track(b, server_root)
    try:
        a_date = a_file.date
    except Exception as e:
        log.debug(f'Error getting date for {a_file}: {e}')
        return None
    try:
        b_date = b_file.date
    except Exception as e:
        log.debug(f'Error getting date for {b_file}: {e}')
        return None

    if a_date > b_date:
        return a
    elif b_date > a_date:
        return b
    return None


def _get_rating(obj) -> float:
    return float(obj._data.attrib.get('userRating', 0))


class PlexQueryException(Exception):
    """Base query exception"""


class InvalidQueryFilter(PlexQueryException):
    """An invalid query filter was provided"""
