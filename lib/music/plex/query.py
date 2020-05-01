"""
:author: Doug Skrypa
"""

import logging
from collections import defaultdict
from itertools import chain
from operator import eq
from typing import TYPE_CHECKING, Collection, Iterator, Set, List, Optional

from plexapi.audio import Track

from ..files.track.track import SongFile
from ..text import Name
from .utils import (
    _show_filters, _resolve_aliases, _resolve_custom_ops, short_repr, _prefixed_filters, _filter_repr, PlexObjTypes
)

if TYPE_CHECKING:
    from .server import LocalPlexServer, PlexObjTypes, PlexObj

__all__ = ['QueryResults', 'PlexQueryException', 'InvalidQueryFilter', 'RawQueryResults']
log = logging.getLogger(__name__)


class RawQueryResults:
    def __init__(self, server: 'LocalPlexServer', obj_type: 'PlexObjTypes', data, library_section_id=None):
        self.server = server
        self._type = obj_type
        self._data = data
        self._library_section_id = library_section_id or data.attrib.get('librarySectionID')

    def __iter__(self):
        return iter(self._data)

    def __repr__(self):
        return f'<{self.__class__.__name__}[{len(self._data):,d} {self._type}s]>'

    def _intermediate_search(self, intm_type: PlexObjTypes, intm_keys, dest_filter: str, kwargs, intm_field='title'):
        intm_kwargs = _intermediate_search_kwargs(kwargs, intm_field, keys=intm_keys)
        custom_filter_keys = '+'.join(sorted(intm_keys))
        msg = f'Performing intermediate search for {intm_type}s matching {_filter_repr(intm_kwargs)}'
        msg += f' - results will be used for custom {self._type} filters: {custom_filter_keys}'
        log.debug(msg, extra={'color': 11})
        results = self.server.music.fetchItems(self.server._ekey(intm_type), **intm_kwargs)
        if self._type == 'album' and dest_filter == 'key__in':
            keys = {'{}/children'.format(a.key) for a in results}
        else:
            keys = {a.key for a in results}

        log.debug(f'Replacing custom filters {custom_filter_keys} with {dest_filter}={short_repr(keys)}')
        if dest_filter in kwargs:
            keys = keys.intersection(kwargs[dest_filter])
            log.debug(f'Merging {dest_filter} values: {short_repr(keys)}')
        kwargs[dest_filter] = keys
        return kwargs

    def _updated_filters(self, kwargs):
        kwargs = _resolve_aliases(kwargs)
        kwargs = _resolve_custom_ops(kwargs)

        if self._type == 'track':
            kwargs = self._apply_track_filters(kwargs)
        else:
            if genre_keys := _prefixed_filters('genre', kwargs):
                for filter_key in genre_keys:
                    if not filter_key.startswith('genre__tag'):
                        target_key = filter_key.replace('genre', 'genre__tag', 1)
                        filter_val = kwargs.pop(filter_key)
                        log.debug(f'Replacing custom filter {filter_key!r} with {target_key}={short_repr(filter_val)}')
                        kwargs[target_key] = filter_val

        if self._type == 'album':
            if artist_keys := _prefixed_filters('artist', kwargs):
                kwargs = self._intermediate_search('artist', artist_keys, 'parentKey__in', kwargs)

        return kwargs

    def _apply_track_filters(self, kwargs):
        if genre_keys := _prefixed_filters('genre', kwargs):
            kwargs = self._intermediate_search('album', genre_keys, 'parentKey__in', kwargs, 'genre__tag')

        if album_keys := _prefixed_filters('album', kwargs):
            kwargs = self._intermediate_search('album', album_keys, 'parentKey__in', kwargs)

        if playlist_keys := _prefixed_filters('in_playlist', kwargs):
            target_key = 'key__in'
            for filter_key in playlist_keys:
                filter_val = kwargs.pop(filter_key)
                lc_val = filter_val.lower()
                for pl_name, playlist in self.server.playlists.items():
                    if pl_name.lower() == lc_val:
                        log.debug(f'Replacing custom filter {filter_key!r} with {target_key}={short_repr(filter_val)}')
                        keys = {track.key for track in playlist.items()}
                        if target_key in kwargs:
                            keys = keys.intersection(kwargs[target_key])
                            log.debug(f'Merged filter={target_key!r} values => {short_repr(keys)}')
                        kwargs[target_key] = keys
                        break
                else:
                    raise ValueError('Invalid playlist: {!r}'.format(filter_val))

        return kwargs

    def _filter(self, data, **kwargs):
        check_attrs = self.server.music._checkAttrs
        return [elem for elem in data if check_attrs(elem, **kwargs)]

    def filter(self, **kwargs) -> 'RawQueryResults':
        if not kwargs:
            return self

        if data := self._data:
            kwargs = self._updated_filters(kwargs)
            if self._type == 'track':
                if artist_keys := _prefixed_filters('artist', kwargs):
                    track_kwargs = {k: v for k, v in kwargs.items() if k not in artist_keys}
                    _show_filters(self._type, track_kwargs)
                    _results = self._filter(data, **track_kwargs)

                    artist_kwargs = _intermediate_search_kwargs(kwargs, keys=artist_keys)
                    artists = self.server._query('artist').filter(**artist_kwargs)
                    artist_keys = {a.attrib['key'][:-9] for a in artists}
                    log.debug(f'Applying album artist filter to tracks: grandparentKey__in={short_repr(artist_keys)}')
                    results = set(self._filter(_results, grandparentKey__in=artist_keys))

                    artist_filters = {key.replace('title', 'originalTitle', 1): v for key, v in artist_kwargs.items()}
                    log.debug(f'Applying non-album artist filter to tracks: {_filter_repr(artist_filters)}')
                    results.update(self._filter(_results, **artist_filters))
                else:
                    _show_filters(self._type, kwargs)
                    results = self._filter(data, **kwargs)
            else:
                _show_filters(self._type, kwargs)
                results = self._filter(data, **kwargs)
        else:
            log.debug(f'No results exist to filter')
            results = []
        # noinspection PyTypeChecker
        return RawQueryResults(self.server, self._type, results, self._library_section_id)

    def results(self) -> List['PlexObj']:
        build_item = self.server.music._buildItemOrNone
        library_section_id = self._library_section_id
        results = list(filter(None, (build_item(elem, None, None) for elem in self._data)))
        for obj in results:
            obj.librarySectionID = library_section_id
        return results

    def result(self) -> Optional['PlexObj']:
        build_item = self.server.music._buildItemOrNone
        for elem in self._data:
            if (obj := build_item(elem, None, None)) is not None:
                obj.librarySectionID = self._library_section_id
                return obj
        return None


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
        if data := [obj._data for obj in self._results]:
            # noinspection PyTypeChecker
            raw = RawQueryResults(self.server, self._type, data, next(iter(self._results)).librarySectionID)
            results = raw.filter(**kwargs).results()
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


def _intermediate_search_kwargs(kwargs, intermediate_field='title', keys=None, prefix=None):
    intm_kwargs = {}
    keys = keys or _prefixed_filters(prefix, kwargs)
    for key in keys:
        filter_val = kwargs.pop(key)
        try:
            base, op = key.rsplit('__', 1)
        except ValueError:
            op = 'contains'
        else:
            if base.endswith('__not'):
                op = 'not__' + op

        intm_kwargs['{}__{}'.format(intermediate_field, op)] = filter_val
    return intm_kwargs


class PlexQueryException(Exception):
    """Base query exception"""


class InvalidQueryFilter(PlexQueryException):
    """An invalid query filter was provided"""
