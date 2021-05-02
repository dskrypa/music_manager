"""
:author: Doug Skrypa
"""

import logging
import re
from collections import defaultdict
from itertools import chain
from operator import eq
from typing import TYPE_CHECKING, Collection, Optional, Any, Union, Iterator
from xml.etree.ElementTree import Element

from ds_tools.output import short_repr
from ..files.track.track import SongFile
from ..text.name import Name
from .exceptions import InvalidQueryFilter
from .filters import check_attrs
from .typing import PlexObjTypes, PlexObj

if TYPE_CHECKING:
    from .server import LocalPlexServer

__all__ = ['QueryResults']
log = logging.getLogger(__name__)
RawResultData = Union[Element, Collection[Element]]

ALIASES = {'rating': 'userRating'}
CUSTOM_OPS = {'__like': 'sregex', '__like_exact': 'sregex', '__not_like': 'nsregex'}


class QueryResults:
    def __init__(self, server: 'LocalPlexServer', obj_type: PlexObjTypes, data: RawResultData, library_section_id=None):
        self.server = server
        self._type = obj_type
        self._data = data
        if library_section_id:
            self._library_section_id = library_section_id
        elif library_section_id := data.attrib.get('librarySectionID'):
            self._library_section_id = int(library_section_id)
        else:
            self._library_section_id = None

    def _new(self, data: RawResultData, obj_type: PlexObjTypes = None) -> 'QueryResults':
        return self.__class__(self.server, obj_type or self._type, data, self._library_section_id)

    def __iter__(self) -> Iterator[Element]:
        return iter(self._data)

    def __repr__(self):
        return f'<{self.__class__.__name__}[{len(self._data):,d} {self._type}s]>'

    def __bool__(self):
        return bool(self._data)

    def __len__(self):
        return len(self._data)

    def __validate(self, other, op):
        if not isinstance(other, self.__class__):
            raise TypeError(f'Unable to {op} results with type={other.__class__.__name__}')
        elif self._type != other._type:
            raise ValueError(f'Unable to {op} results for incompatible types ({self._type}, {other._type})')
        elif self.server != other.server:
            raise ValueError(f'Unable to {op} results from different servers ({self.server}, {other.server})')

    def __add__(self, other):
        self.__validate(other, 'combine')
        return self._new(set(self._data).union(other._data))

    def __iadd__(self, other):
        self.__validate(other, 'combine')
        self._data = set(self._data).union(other._data)
        return self

    def __sub__(self, other):
        self.__validate(other, 'remove')
        return self._new(set(self._data).difference(other._data))

    def __isub__(self, other):
        self.__validate(other, 'remove')
        self._data = set(self._data).difference(other._data)
        return self

    def _query(self, obj_type: PlexObjTypes, **kwargs):
        return self.server.query(obj_type, **kwargs)

    def __serializable__(self):
        return self.results()

    def keys(self, trim=None, level='key', suffix=None) -> set[str]:
        keys = {o.attrib[level] for o in self._data} if trim is None else {o.attrib[level][:trim] for o in self._data}
        if suffix:
            keys = {f'{key}{suffix}' for key in keys}
        return keys

    def items(self, trim=None) -> Iterator[tuple[str, Element]]:
        if trim is None:
            for obj in self._data:
                yield obj.attrib['key'], obj
        else:
            for obj in self._data:
                yield obj.attrib['key'][:trim], obj

    def key_map(self, trim=None) -> dict[str, Element]:
        return dict(self.items(trim))

    def in_playlist(self, name: str) -> 'QueryResults':
        if not self._type == 'track':
            raise InvalidQueryFilter(f'in_playlist() is only permitted for track results')

        playlist = self.server.playlist(name)
        track_keys = {track.key for track in playlist.items()}          # Note: .items() is a Playlist method, not dict
        return self._new([obj for key, obj in self.items() if key in track_keys])

    def with_genre(self, **kwargs) -> 'QueryResults':
        for key in list(kwargs):
            if key.startswith('genre') and not key.startswith('genre__tag'):
                kwargs[key.replace('genre', 'genre__tag', 1)] = kwargs.pop(key)

        if self._type == 'track':
            album_keys = self._query('album', **kwargs).keys(-9)
            return self._new(self._filter(self._data, parentKey__in=album_keys))
        else:
            return self._new(self._filter(self._data, **kwargs))

    def from_album(self, **kwargs):
        if not self._type == 'track':
            raise InvalidQueryFilter(f'from_album() is only permitted for track results')
        album_keys = self._query('album', **kwargs).keys(-9)
        return self._new(self._filter(self._data, parentKey__in=album_keys))

    def from_artist(self, **kwargs):
        artist_keys = self._query('artist', **kwargs).keys(-9)
        if self._type == 'album':
            return self._new(self._filter(self._data, parentKey__in=artist_keys))
        elif self._type == 'track':
            results = set(self._filter(self._data, 'album artist', grandparentKey__in=artist_keys))
            artist_filters = {key.replace('title', 'originalTitle', 1): val for key, val in kwargs.items()}
            results.update(self._filter(self._data, 'non-album artist', **artist_filters))
            return self._new(results)
        else:
            raise InvalidQueryFilter(f'from_artist() is only permitted for track and album results')

    def _apply_custom_filters(self, kwargs) -> 'QueryResults':
        result = self
        if in_playlist := kwargs.pop('in_playlist', None):
            result = result.in_playlist(in_playlist)
        if genre_keys := _prefixed_filters('genre', kwargs):
            result = result.with_genre(**_extract_kwargs(kwargs, genre_keys, 'genre__tag'))
        if artist_keys := _prefixed_filters('artist', kwargs):
            result = result.from_artist(**_extract_kwargs(kwargs, artist_keys))
        if result._type == 'track':
            if album_keys := _prefixed_filters('album', kwargs):
                result = result.from_album(**_extract_kwargs(kwargs, album_keys))
        return result

    def _filter(self, data: RawResultData, msg: Optional[str] = None, **kwargs):
        final_filters = '\n'.join(f'    {key}={short_repr(val)}' for key, val in sorted(kwargs.items()))
        msg = msg or 'the following'
        log.debug(f'Applying {msg} filters to {self._type}s:\n{final_filters}')
        return [elem for elem in data if check_attrs(elem, **kwargs)]

    def filter(self, **kwargs) -> 'QueryResults':
        if not kwargs:
            return self

        kwargs = _resolve_custom_ops(_resolve_aliases(kwargs))
        result = self._apply_custom_filters(kwargs)
        if data := result._data:
            results = self._filter(data, **kwargs)
        else:
            log.debug(f'No results exist to filter')
            results = []

        return self._new(results)

    def results(self) -> set[PlexObj]:
        build_item = self.server.music._buildItemOrNone
        library_section_id = self._library_section_id
        results = set(filter(None, (build_item(elem, None, None) for elem in self._data)))
        for obj in results:
            obj.librarySectionID = library_section_id
        return results

    def result(self) -> Optional[PlexObj]:
        build_item = self.server.music._buildItemOrNone
        for elem in self._data:
            if (obj := build_item(elem, None, None)) is not None:
                obj.librarySectionID = self._library_section_id
                return obj
        return None

    def artists(self, **kwargs) -> 'QueryResults':
        if self._type == 'artist':
            return self.filter(**kwargs)
        elif self._type == 'album':
            artist_keys = self.keys(level='parentKey', suffix='/children')
        elif self._type == 'track':
            artist_keys = self.keys(level='grandparentKey', suffix='/children')
        else:
            raise InvalidQueryFilter(f'artists() is only permitted for track, album, and artist results')
        return self._query('artist', key__in=artist_keys, **kwargs)

    def albums(self, **kwargs) -> 'QueryResults':
        if self._type == 'album':
            return self.filter(**kwargs)
        elif self._type == 'artist':
            return self._query('album', parentKey__in=self.keys(-9), **kwargs)
        elif self._type == 'track':
            return self._query('album', key__in=self.keys(level='parentKey', suffix='/children'), **kwargs)
        else:
            raise InvalidQueryFilter(f'albums() is only permitted for track, album, and artist results')

    def tracks(self, **kwargs) -> 'QueryResults':
        if self._type == 'track':
            return self.filter(**kwargs)
        elif self._type == 'artist':
            return self._query('track', grandparentKey__in=self.keys(-9), **kwargs)
        elif self._type == 'album':
            return self._query('track', parentKey__in=self.keys(-9), **kwargs)
        else:
            raise InvalidQueryFilter(f'tracks() is only permitted for track, album, and artist results')

    def with_rating(self, rating, op=eq) -> 'QueryResults':
        return self._new({obj for obj in self._data if op(float(obj.attrib.get('userRating', 0)), rating)})

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
            raise InvalidQueryFilter('unique() is only permitted for track results')

        artist_title_obj_map = defaultdict(dict)
        for track in self._data:
            td = track.attrib
            if (artist := td['grandparentTitle']) == 'Various Artists':
                try:
                    artist = td['originalTitle']
                except KeyError:
                    pass

            title_obj_map = artist_title_obj_map[artist]
            lc_title = td['title'].lower()
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
                    track_name = name_from_enclosed(track.attrib['title'])
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

        return self._new(results)


def _pick_uniq_track(existing: Element, track: Element, server, rated, latest, singles) -> Element:
    if rated:
        if existing.attrib.get('userRating') and not track.attrib.get('userRating'):
            # log.debug(f'Keeping {existing=} instead of {track=} because of rating', extra={'color': 11})
            return existing
        elif not existing.attrib.get('userRating') and track.attrib.get('userRating'):
            # log.debug(f'Keeping {track=} instead of {existing=} because of rating', extra={'color': 11})
            return track
        elif latest and (latest_track := _get_latest(existing, track, server.server_root, singles)):
            # if latest_track == existing:
            #     log.debug(f'Keeping {existing=} instead of {track=} because of date', extra={'color': 11})
            # else:
            #     log.debug(f'Keeping {track=} instead of {existing=} because of date', extra={'color': 11})
            # noinspection PyUnboundLocalVariable
            return latest_track
        else:                                                           # Ensure the chosen value is stable between runs
            return min(existing, track, key=lambda e: int(e.attrib['ratingKey']))
    elif latest and (latest_track := _get_latest(existing, track, server.server_root, singles)):
        # if latest_track == existing:
        #     log.debug(f'Keeping {existing=} instead of {track=} because of date', extra={'color': 11})
        # else:
        #     log.debug(f'Keeping {track=} instead of {existing=} because of date', extra={'color': 11})
        # noinspection PyUnboundLocalVariable
        return latest_track
    else:                                                               # Ensure the chosen value is stable between runs
        return min(existing, track, key=lambda e: int(e.attrib['ratingKey']))


def _get_latest(a: Element, b: Element, server_root, singles):
    a_path = a[0][0].attrib['file']
    b_path = b[0][0].attrib['file']
    if singles:
        a_path_lc = a_path.lower()
        b_path_lc = b_path.lower()
        if '/singles/' in a_path_lc and '/singles/' not in b_path_lc:
            return b
        elif '/singles/' in b_path_lc and '/singles/' not in a_path_lc:
            return a

    a_file = SongFile.for_plex_track(a_path, server_root)
    b_file = SongFile.for_plex_track(b_path, server_root)
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

    try:
        if a_date > b_date:
            return a
        elif b_date > a_date:
            return b
    except TypeError:
        pass
    return None


def _prefixed_filters(field, filters):
    us_key = '{}__'.format(field)
    return {k for k in filters if k == field or k.startswith(us_key)}


def _extract_kwargs(kwargs, keys, intermediate_field='title'):
    intm_kwargs = {}
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


def _resolve_aliases(kwargs):
    for key, val in list(kwargs.items()):
        base = key
        op = None
        if '__' in key:
            base, op = key.split('__', maxsplit=1)
        try:
            real_key = ALIASES[base]
        except KeyError:
            pass
        else:
            del kwargs[key]
            if op:
                real_key = f'{real_key}__{op}'
            kwargs[real_key] = val
            log.debug(f'Resolved query alias={key!r} => {real_key}={short_repr(val)}')

    return kwargs


def _resolve_custom_ops(kwargs):
    # Replace custom/shorthand ops with the real operators
    for filter_key, filter_val in sorted(kwargs.items()):
        keyword = next((val for val in CUSTOM_OPS if filter_key.endswith(val)), None)
        if keyword:
            kwargs.pop(filter_key)
            target_key = '{}__{}'.format(filter_key[:-len(keyword)], CUSTOM_OPS[keyword])
            if keyword == '__like' and isinstance(filter_val, str):
                filter_val = filter_val.replace(' ', '.*?')
            filter_val = re.compile(filter_val, re.IGNORECASE) if isinstance(filter_val, str) else filter_val
            log.debug(f'Replacing custom op={filter_key!r} with {target_key}={short_repr(filter_val)}')
            kwargs[target_key] = filter_val

    return kwargs


def _merge_filters(kwargs: dict[str, Any], key: str, value: Any, union=False):
    if key in kwargs:
        current = kwargs[key]
        if key.endswith('__in'):
            if not isinstance(current, set):
                current = set(current)

            value = current.union(value) if union else current.intersection(value)
            log.debug(f'Merged filter={key!r} values => {short_repr(value)}')

    kwargs[key] = value
    return kwargs
