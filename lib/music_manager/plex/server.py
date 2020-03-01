"""
Local Plex server client implementation.

:author: Doug Skrypa
"""

import logging
import re
from collections import defaultdict
from configparser import NoSectionError
from functools import partialmethod
from getpass import getpass
from pathlib import Path

from plexapi import PlexConfig, DEFAULT_CONFIG_PATH
from plexapi.myplex import MyPlexAccount
from plexapi.playlist import Playlist
from plexapi.server import PlexServer
from plexapi.utils import SEARCHTYPES
from requests import Session
from urllib3 import disable_warnings as disable_urllib3_warnings

from ds_tools.compat import cached_property
from ds_tools.core import get_input
from ds_tools.unicode import LangCat
from ds_tools.output import short_repr, bullet_list
from ..files.track.track import SongFile
from .patches import apply_plex_patches
from .utils import stars

__all__ = ['LocalPlexServer']
log = logging.getLogger(__name__)

disable_urllib3_warnings()
apply_plex_patches()

CUSTOM_FILTERS_BASE = {
    'genre': ('album', 'genre__tag', {'track': 'parentKey'}),
    'album': ('album', 'title', {'track': 'parentKey'}),
    'artist': ('artist', 'title', {'album': 'parentKey'}),
    'in_playlist': ('playlist', 'title', {})
}
CUSTOM_FILTERS_TRACK_ARTIST = {
    'artist': ('artist', 'title', {'track': 'grandparentKey'}),
}
CUSTOM_OPS = {
    '__like': 'sregex',
    '__like_exact': 'sregex',
    '__not_like': 'nsregex'
}
ALIASES = {
    'rating': 'userRating'
}


class LocalPlexServer:
    def __init__(self, url=None, user=None, server_path_root=None, config_path=DEFAULT_CONFIG_PATH, music_library=None):
        self._config_path = Path(config_path).expanduser().resolve()
        log.debug(f'Reading PlexAPI config from {self._config_path}')
        if not self._config_path.exists():
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            self._config_path.touch()
        self._config = PlexConfig(self._config_path)
        self.url = self._get_config('auth', 'server_baseurl', 'server url', url, required=True)
        need_user = not self._config.get('auth.server_token')
        self.user = self._get_config('auth', 'myplex_username', 'username', user, required=need_user)
        server_path_root = self._get_config('custom', 'server_path_root', new_value=server_path_root)
        self.server_root = Path(server_path_root) if server_path_root else None
        self.music_library = self._get_config('custom', 'music_lib_name', new_value=music_library) or 'Music'

    @cached_property
    def _token(self):
        token = self._get_config('auth', 'server_token')
        if not token:
            account = MyPlexAccount(self.user, getpass('Plex password:'))
            token = account._token
            self._set_config('auth', 'server_token', token)
        return token

    def _get_config(self, section, key, name=None, new_value=None, save=False, required=False):
        name = name or key
        cfg_value = self._config.get(f'{section}.{key}')
        if cfg_value and new_value:
            msg = f'Found {name}={cfg_value!r} in {self._config_path} - overwrite with {name}={new_value!r}?'
            if get_input(msg, skip=save):
                self._set_config(section, key, new_value)
        elif required and not cfg_value and not new_value:
            try:
                new_value = input(f'Please enter your Plex {name}: ').strip()
            except EOFError as e:
                raise RuntimeError('Unable to read stdin (this is often caused by piped input)') from e
            if not new_value:
                raise ValueError(f'Invalid {name}')
            self._set_config(section, key, new_value)
        return new_value or cfg_value

    def _set_config(self, section, key, value):
        try:
            self._config.set(section, key, value)
        except NoSectionError:
            self._config.add_section(section)
            self._config.set(section, key, value)
        with self._config_path.open('w', encoding='utf-8') as f:
            self._config.write(f)

    @cached_property
    def _session(self):
        session = Session()
        session.verify = False
        return PlexServer(self.url, self._token, session=session)

    @cached_property
    def music(self):
        return self._session.library.section(self.music_library)

    def _ekey(self, search_type):
        return '/library/sections/1/all?type={}'.format(SEARCHTYPES[search_type])

    def find_songs_by_rating_gte(self, rating, **kwargs):
        """
        :param int rating: Song rating on a scale of 0-10
        :return list: List of :class:`plexapi.audio.Track` objects
        """
        # noinspection PyCallingNonCallable
        return self.get_tracks(userRating__gte=rating, **kwargs)

    def find_song(self, path):
        return self.get_track(media__part__file=path)

    def get_artists(self, name, mode='contains', **kwargs):
        kwargs.setdefault('title__{}'.format(mode), name)
        return self.find_objects('artist', **kwargs)

    def get_albums(self, name, mode='contains', **kwargs):
        kwargs.setdefault('title__{}'.format(mode), name)
        return self.find_objects('album', **kwargs)

    def find_object(self, obj_type, **kwargs):
        ekey = self._ekey(obj_type)
        for kwargs in self._updated_filters(obj_type, kwargs):
            _show_filters(kwargs)
            return self.music.fetchItem(ekey, **kwargs)

    def find_objects(self, obj_type, **kwargs):
        ekey = self._ekey(obj_type)
        if obj_type == 'track':
            results = set()
            for kwargs in self._updated_filters(obj_type, kwargs):
                _show_filters(kwargs)
                results.update(self.music.fetchItems(ekey, **kwargs))
            return results
        else:
            kwargs = next(self._updated_filters(obj_type, kwargs))
            _show_filters(kwargs)
            return self.music.fetchItems(ekey, **kwargs)

    get_track = partialmethod(find_object, 'track')
    get_tracks = partialmethod(find_objects, 'track')

    @property
    def playlists(self):
        return {p.title: p for p in self._session.playlists()}

    def create_playlist(self, name, items):
        if not items:
            raise ValueError('An iterable containing one or more tracks/items must be provided')
        return Playlist.create(self._session, name, items)

    def sync_playlist(self, name, **criteria):
        expected = self.get_tracks(**criteria)
        playlists = self.playlists
        add_fmt = 'Adding {:,d} tracks to playlist {} ({:,d} tracks => {:,d}):'
        rm_fmt = 'Removing {:,d} tracks from playlist {} ({:,d} tracks => {:,d}):'
        if name not in playlists:
            log.info('Creating playlist {} with {:,d} tracks'.format(name, len(expected)), extra={'color': 10})
            log.debug('Creating playlist {} with tracks: {}'.format(name, expected))
            plist = self.create_playlist(name, expected)
        else:
            plist = playlists[name]
            plist_items = plist.items()
            size = len(plist_items)

            to_rm = []
            for track in plist_items:
                if track not in expected:
                    to_rm.append(track)

            if to_rm:
                log.info(rm_fmt.format(len(to_rm), name, size, size - len(to_rm)), extra={'color': 13})
                print(bullet_list(to_rm))
                size -= len(to_rm)
                # for track in to_remove:
                #     plist.removeItem(track)
                plist.removeItems(to_rm)
            else:
                log.log(19, 'Playlist {} does not contain any tracks that should be removed'.format(name))

            to_add = []
            for track in expected:
                if track not in plist_items:
                    to_add.append(track)

            if to_add:
                log.info(add_fmt.format(len(to_add), name, size, size + len(to_add)), extra={'color': 14})
                print(bullet_list(to_add))
                plist.addItems(to_add)
                size += len(to_add)
            else:
                log.log(19, 'Playlist {} is not missing any tracks'.format(name))

            if not to_add and not to_rm:
                fmt = 'Playlist {} contains {:,d} tracks and is already in sync with the given criteria'
                log.info(fmt.format(name, len(plist_items)), extra={'color': 11})

    def sync_ratings_to_files(self, path_filter=None, dry_run=False):
        """
        Sync the song ratings from this Plex server to the files

        :param str path_filter: String that file paths must contain to be sync'd
        :param bool dry_run: Dry run - print the actions that would be taken instead of taking them
        """
        if self.server_root is None:
            raise ValueError(f'The custom.server_path_root is missing from {self._config_path} and wasn\'t provided')
        prefix = '[DRY RUN] Would update' if dry_run else 'Updating'
        kwargs = {'media__part__file__icontains': path_filter} if path_filter else {}
        for track in self.find_songs_by_rating_gte(1, **kwargs):
            file = SongFile.for_plex_track(track, self.server_root)
            file_stars = file.star_rating_10
            plex_stars = track.userRating
            if file_stars == plex_stars:
                log.log(9, 'Rating is already correct for {}'.format(file))
            else:
                log.info('{} rating from {} to {} for {}'.format(prefix, file_stars, plex_stars, file))
                if not dry_run:
                    file.star_rating_10 = plex_stars

    def sync_ratings_from_files(self, path_filter=None, dry_run=False):
        """
        Sync the song ratings on this Plex server with the ratings in the files

        :param str path_filter: String that file paths must contain to be sync'd
        :param bool dry_run: Dry run - print the actions that would be taken instead of taking them
        """
        if self.server_root is None:
            raise ValueError(f'The custom.server_path_root is missing from {self._config_path} and wasn\'t provided')
        prefix = '[DRY RUN] Would update' if dry_run else 'Updating'
        kwargs = {'media__part__file__icontains': path_filter} if path_filter else {}
        for track in self.get_tracks(**kwargs):
            file = SongFile.for_plex_track(track, self.server_root)
            file_stars = file.star_rating_10
            if file_stars is not None:
                plex_stars = track.userRating
                if file_stars == plex_stars:
                    log.log(9, 'Rating is already correct for {}'.format(file))
                else:
                    log.info('{} rating from {} to {} for {}'.format(prefix, plex_stars, file_stars, file))
                    if not dry_run:
                        track.edit(**{'userRating.value': file_stars})

    def _updated_filters(self, obj_type, kwargs):
        """
        Update the kwarg search filters for a fetchItem/fetchItems call using custom search filters.

        Implemented custom filters:
         - *__like: Automatically compiles the given str value as a regex pattern and replaces 'like' with the custom
           sregex filter function, which uses pattern.search() instead of re.match()
         - *__not_like: Like __like, but translates to nsregex
         - genre: Plex stores genres at the album and artist level rather than the track level - this filter first runs
           a search for albums that match the given value, then adds a filter to the track search so that only tracks
           that are in the albums with the given genre are returned.
         - artist/album: Rather than needing to chain searches manually where artist/album objects are passed as the
           values, they can now be provided as strings.  Similar to the genre search, a separate search is run first for
           finding artists/albums that match the given value, then tracks from/in the given criteria are found by using
           the parentKey__in/grandparentKey__in filters, respectfully.  In theory, this should be more efficient than
           using the parentTitle/grandparentTitle filters, since any regex operations only need to be done on the
           album/artist titles once instead of on each track's album/artist titles, and the track search can use a O(1)
           set lookup against the discovered parent/grandparent keys.

        :param dict kwargs: The kwargs that were passed to :meth:`.get_tracks` or a similar method
        :return dict: Modified kwargs with custom search filters
        """
        exclude_rated_dupes = kwargs.pop('exclude_rated_dupes', False)
        kwargs = _resolve_aliases(kwargs)
        kwargs = _resolve_custom_ops(kwargs)

        # If excluding rated dupes, search for the tracks that were rated and have the same titles as unrated tracks
        if exclude_rated_dupes and obj_type == 'track' and 'userRating' in kwargs:
            kwargs['custom__custom'] = self.__get_dupe_filter(kwargs)

        kwargs = self.__apply_custom_filters(obj_type, kwargs, CUSTOM_FILTERS_BASE)
        if obj_type == 'track':
            artist_keys = _prefixed_filters('artist', kwargs)
            if artist_keys:
                yield self.__apply_custom_filters(obj_type, kwargs.copy(), CUSTOM_FILTERS_TRACK_ARTIST)
                filter_repl_fmt = 'Replacing custom filter {!r} with {}={}'
                for filter_key in artist_keys:
                    artist_key = filter_key.replace('artist', 'originalTitle', 1)
                    filter_val = kwargs.pop(filter_key)
                    log.debug(filter_repl_fmt.format(filter_key, artist_key, short_repr(filter_val)))
                    kwargs[artist_key] = filter_val
                yield kwargs
            else:
                yield kwargs
        else:
            yield kwargs

    def __apply_custom_filters(self, obj_type, kwargs, filters):
        # Perform intermediate searches that are necessary for custom filters
        filter_repl_fmt = 'Replacing custom filter {!r} with {}={}'
        for kw, (ekey, field, targets) in sorted(filters.items()):
            try:
                target_key = '{}__in'.format(targets[obj_type])
            except KeyError:
                if kw == 'genre':  # tracks need to go by their parents' genre, but albums/artists can use their own
                    for filter_key in _prefixed_filters(kw, kwargs):
                        if filter_key.startswith('genre') and not filter_key.startswith('genre__tag'):
                            target_key = filter_key.replace('genre', 'genre__tag', 1)
                            filter_val = kwargs.pop(filter_key)
                            log.debug(filter_repl_fmt.format(filter_key, target_key, short_repr(filter_val)))
                            kwargs[target_key] = filter_val
                elif kw == 'in_playlist':
                    target_key = 'key__in'
                    for filter_key in _prefixed_filters(kw, kwargs):
                        filter_val = kwargs.pop(filter_key)
                        lc_val = filter_val.lower()
                        for pl_name, playlist in self.playlists.items():
                            if pl_name.lower() == lc_val:
                                log.debug(filter_repl_fmt.format(filter_key, target_key, short_repr(filter_val)))
                                keys = {track.key for track in playlist.items()}
                                if target_key in kwargs:
                                    keys = keys.intersection(kwargs[target_key])
                                    log.debug('Merged filter={!r} values => {}'.format(target_key, short_repr(keys)))
                                kwargs[target_key] = keys
                                break
                        else:
                            raise ValueError('Invalid playlist: {!r}'.format(filter_val))
            else:
                log.debug(f'custom filter kw={kw!r} for obj_type={obj_type!r} has target_key={target_key!r}')
                kw_keys = _prefixed_filters(kw, kwargs)
                if kw_keys:
                    ekey_filters = {}
                    for filter_key in kw_keys:
                        filter_val = kwargs.pop(filter_key)
                        try:
                            base, op = filter_key.rsplit('__', 1)
                        except ValueError:
                            op = 'contains'
                        else:
                            if base.endswith('__not'):
                                op = 'not__' + op

                        ekey_filters['{}__{}'.format(field, op)] = filter_val

                    custom_filter_keys = '+'.join(sorted(kw_keys))

                    fmt = 'Performing intermediate search for custom filters={}: ekey={!r} with filters={}'
                    filter_repr = ', '.join('{}={}'.format(k, short_repr(v)) for k, v in ekey_filters.items())
                    log.debug(fmt.format(ekey, custom_filter_keys, filter_repr))

                    results = self.music.fetchItems(self._ekey(ekey), **ekey_filters)
                    if obj_type == 'album' and target_key == 'key__in':
                        keys = {'{}/children'.format(a.key) for a in results}
                    else:
                        keys = {a.key for a in results}

                    fmt = 'Replacing custom filters {} with {}={}'
                    log.debug(fmt.format(custom_filter_keys, target_key, short_repr(keys)))
                    if target_key in kwargs:
                        keys = keys.intersection(kwargs[target_key])
                        log.debug('Merging {} values: {}'.format(target_key, short_repr(keys)))
                    kwargs[target_key] = keys

        return kwargs

    def __get_dupe_filter(self, kwargs):
        dupe_kwargs = kwargs.copy()
        dupe_kwargs.pop('userRating')
        dupe_kwargs['userRating__gte'] = 1
        rated_tracks = self.music.fetchItems(self._ekey('track'), **dupe_kwargs)
        rated_tracks_by_artist_key = defaultdict(set)
        for track in rated_tracks:
            rated_tracks_by_artist_key[track.grandparentKey].add(track.title.lower())

        pat = re.compile(r'(.*)\((?:Japanese|JP|Chinese|Mandarin)\s*(?:ver\.?(?:sion))?\)$', re.IGNORECASE)

        def _filter(elem_attrib):
            titles = rated_tracks_by_artist_key[elem_attrib['grandparentKey']]
            if not titles:
                return True
            title = elem_attrib['title'].lower()
            if title in titles:
                return False
            m = pat.match(title)
            if m and m.group(1).strip() in titles:
                return False
            part = next((t for t in titles if t.startswith(title) or title.startswith(t)), None)
            if not part:
                return True
            elif len(part) > len(title):
                return title not in LangCat.split(part)
            return part not in LangCat.split(title)

        # return lambda a: a['title'] not in rated_tracks_by_artist_key[a['grandparentKey']]
        return _filter


def _show_filters(filters):
    final_filters = '\n'.join(f'    {key}={short_repr(val)}' for key, val in sorted(filters.items()))
    log.debug(f'Final filters:\n{final_filters}')


def _prefixed_filters(field, filters):
    us_key = '{}__'.format(field)
    return {k for k in filters if k == field or k.startswith(us_key)}


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
            log.debug('Replacing custom op {!r} with {}={}'.format(filter_key, target_key, short_repr(filter_val)))
            kwargs[target_key] = filter_val

    return kwargs


def print_song_info(songs):
    for song in songs:
        print('{} - {} - {} - {}'.format(stars(song.userRating), song.artist().title, song.album().title, song.title))