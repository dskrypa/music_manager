"""
Patches for PlexAPI

:author: Doug Skrypa
"""

import logging
import warnings
from datetime import datetime, timedelta
from functools import cached_property, partial
from hashlib import sha256
from inspect import getsource
from typing import Callable
from urllib.parse import urlencode
from xml.etree.ElementTree import Element

from plexapi import __version__ as PLEX_API_VERSION
from plexapi.audio import Track, Album, Artist, Audio
from plexapi.base import PlexObject, Playable, PlexPartialObject, PlexSession, MediaContainer, PlexHistory
from plexapi.base import _DONT_RELOAD_FOR_KEYS, USER_DONT_RELOAD_FOR_KEYS
from plexapi.exceptions import UnknownType
from plexapi.media import Media, Field, Mood, Collection, Label, Guid, Chapter, Genre, Country, Similar, Style, Format
from plexapi.media import Subformat
from plexapi.utils import toDatetime, cast, iterXMLBFS, getPlexObject

from ..common.ratings import stars
from ..common.utils import deinit_colorama as _deinit_colorama
from .filters import get_attr_operator, get_attr_value, ele_matches_filters

__all__ = ['apply_plex_patches']
log = logging.getLogger(__name__)

PATCHED_VERSION = '4.15.14'
_APPLIED_BASIC_PATCHES = False
_APPLIED_PERF_PATCHES = False
_NotSet = object()


def apply_plex_patches(deinit_colorama: bool = True, skip_changed: bool = True, perf_patches: bool = True):
    """
    Monkey-patch...
      - Track, Album, and Artist to have more readable/useful reprs
      - PlexObject to be sortable
      - PlexObject to have an as_dict() method

    :param deinit_colorama: plexapi.utils imports tqdm (it uses it to print a progress bar during downloads); when
      importing tqdm, tqdm imports and initializes colorama.  Colorama ends up raising exceptions when piping output to
      ``| head``.  Defaults to True.
    :param skip_changed: Skip performance patches if the source method changed since the patch was written
    :param perf_patches: Apply _loadData patches for Track and its parent classes
    """
    if deinit_colorama:
        _deinit_colorama()

    global _APPLIED_BASIC_PATCHES
    if _APPLIED_BASIC_PATCHES:
        log.debug('Skipping plex basic patches - they were already applied')
    else:
        _apply_plex_patches()
        _APPLIED_BASIC_PATCHES = True

    if perf_patches:
        apply_perf_patches(skip_changed)


def apply_perf_patches(skip_changed: bool = True):
    """
    :param skip_changed: Skip performance patches if the source method changed since the patch was written
    """
    global _APPLIED_PERF_PATCHES
    if _APPLIED_PERF_PATCHES:
        log.debug('Skipping plex perf patches - they were already applied')
    else:
        _apply_perf_patches(skip_changed)
        _APPLIED_PERF_PATCHES = True


def _apply_plex_patches():
    def album_repr(self) -> str:
        rating = stars(float(self._data.attrib.get('userRating', 0)))
        genres = ', '.join(g.tag for g in self.genres)
        artist = self.parentTitle
        return f'<{self.__class__.__name__}#{self._int_key}[{rating}]({self.title!r}, {artist=}, {genres=!s})>'

    def artist_repr(self) -> str:
        rating = stars(float(self._data.attrib.get('userRating', 0)))
        genres = ', '.join(g.tag for g in self.genres)
        return f'<{self.__class__.__name__}#{self._int_key}[{rating}]({self.title!r}, {genres=!s})>'

    def track_repr(self, rating=None) -> str:
        rating = stars(rating or self.userRating or 0)
        artist = self.originalTitle if self.grandparentTitle == 'Various Artists' else self.grandparentTitle
        album = self.parentTitle
        return f'<{self.__class__.__name__}#{self._int_key}[{rating}]({self.title!r}, {artist=}, {album=})>'

    def full_info(ele):
        return {'_type': ele.tag, 'attributes': ele.attrib, 'elements': [full_info(e) for e in ele]}

    PlexObject._int_key = cached_property(lambda self: int(self._clean(self.key)))
    PlexObject._int_key.__set_name__(PlexObject, '_int_key')
    PlexObject.__lt__ = lambda self, other: self._int_key < other._int_key
    PlexObject.as_dict = lambda self: full_info(self._data)

    Track.__repr__ = track_repr
    Album.__repr__ = album_repr
    Artist.__repr__ = artist_repr


def _apply_perf_patches(skip_changed: bool = True):
    # region Load Data Method Patches

    def audio_load_data(self: Audio, data: Element):
        """ Load attribute values from Plex XML response. """
        self._data = data  # All attributes based on this data are now implemented as descriptors below

    def playable_load_data(self: Playable, data: Element):
        pass  # Only 2 attributes were set here, and both are now descriptors

    def session_load_data(self: PlexSession, data: Element):
        get_attrib = data.attrib.get
        self.live = cast_bool(get_attrib('live', '0'))
        self.player = player = find_item(self, data, etag='Player')  # self.findItem(data, etag='Player')
        self.session = session = find_item(self, data, etag='Session')  # self.findItem(data, etag='Session')
        self.sessionKey = cast_num(int, get_attrib('sessionKey'))
        self.transcodeSession = tc_session = find_item(self, data, etag='TranscodeSession')  # self.findItem(data, etag='TranscodeSession')

        get_user_attrib = data.find('User').attrib.get
        self._username = username = get_user_attrib('title')
        self._userId = cast_num(int, get_user_attrib('id'))

        # For backwards compatibility
        self.players = [player] if player else []
        self.sessions = [session] if session else []
        self.transcodeSessions = [tc_session] if tc_session else []
        self.usernames = [username] if username else []

    def track_load_data(self: Track, data: Element):
        """ Load attribute values from Plex XML response. """
        self._data = data
        # The calls to `Audio._loadData(self, data)` and `Playable._loadData(self, data)` are skipped since all attrs
        # based on this data are implemented as descriptors now

    def album_load_data(self: Album, data: Element):
        self._data = data
        self.key = self.key.replace('/children', '')  # FIX_BUG_50

    def artist_load_data(self: Artist, data: Element):
        self._data = data
        self.key = self.key.replace('/children', '')  # FIX_BUG_50
        self.locations = self.listAttrs(data, 'path', etag='Location')

    # endregion

    # region PlexObject Method Patches

    _get_attr_operator = staticmethod(get_attr_operator)
    _get_attr_value = staticmethod(get_attr_value)
    _check_attrs = staticmethod(ele_matches_filters)

    false = {False, 0, '0'}

    def build_details_key(self, **kwargs):
        """ Builds the details key with the XML include parameters.
            All parameters are included by default with the option to override each parameter
            or disable each parameter individually by setting it to False or 0.
        """
        if not (details_key := self.key):
            return details_key

        if cls_includes := getattr(self, '_INCLUDES', None):
            if kwargs:
                params = {
                    1 if value is True else value
                    for k, v in cls_includes.items()
                    if (value := kwargs.pop(k, v)) not in false
                }
            else:
                params = cls_includes.copy()
        else:
            params = {}

        if kwargs and (cls_excludes := getattr(self, '_EXCLUDES', None)):
            params |= {k: 1 if v is True else v for k in cls_excludes if (v := kwargs.pop(k, None)) is not None}

        if params:
            details_key += '?' + urlencode(sorted(params.items()))

        return details_key

    # endregion

    # region PlexPartialObject Method Patches

    no_reload = _DONT_RELOAD_FOR_KEYS.union(USER_DONT_RELOAD_FOR_KEYS)
    real_get_attribute = object.__getattribute__

    def get_attribute(self: PlexPartialObject, attr: str):
        # Dragons inside.. :-/
        if attr.startswith('_') or attr in no_reload:
            return real_get_attribute(self, attr)  # Optimized case for simple conditions - skip storing in a var

        # Check a few cases where we don't want to reload
        if (value := real_get_attribute(self, attr)) or (value is not None and value != []):
            return value
        elif not self.key or (self._details_key or self.key) == self._initpath:  # == self.isFullObject()
            return value
        elif not self._autoReload or isinstance(self, (PlexSession, PlexHistory)):
            return value

        # Log the reload.
        title = self.__dict__.get('title') or self.__dict__.get('name')
        obj_name = f'{self.__class__.__name__} {title!r}' if title else self.__class__.__name__
        log.debug(f'Reloading {obj_name} for {attr=}')
        # Reload and return the value
        self._reload(_overwriteNone=False)
        return real_get_attribute(self, attr)

    # endregion

    # region Patch Target Change Checks

    data_attr_patches = {
        Audio: patch_audio_data_attrs,
        Playable: patch_playable_data_attrs,
        Track: patch_track_data_attrs,
        Album: patch_album_data_attrs,
        Artist: patch_artist_data_attrs,
    }

    # Last updated for PlexAPI version: 4.15.14 (2024-07-06)
    # Compare between tags example: https://github.com/pkkid/python-plexapi/compare/4.13.2...4.15.14
    perf_patches = [
        (Audio, '_loadData', audio_load_data, '6614f35f02b7f0c0b0e73f5c54323ee866058b7e8f02b3d554252368ce7575d5'),
        (Playable, '_loadData', playable_load_data, 'c24c0ced7e444c08e8967b92353309b58df113a7373f6b876e8c7d8d77ffe234'),
        (Track, '_loadData', track_load_data, '0b7dc3f3f34c402da635015eec4441a540b8d22e88759480744a9f477130a5d7'),
        (Album, '_loadData', album_load_data, 'c9211a2d0183cc9a3411df9738cf1746e08bbe64d2b87b404b4878a31070ebbf'),
        (Artist, '_loadData', artist_load_data, 'a46ae9584183ae07e5fc492cf6e055e2351090364d00785ec8cf94159de15023'),
        (PlexSession, '_loadData', session_load_data, '249132147cc678ff7b0f9aeb078baedeb0bb52e023586458be75816bc50b2f9c'),
        (PlexObject, '_getAttrOperator', _get_attr_operator, '8379d358737730f32cae86016d812eae676305801367d7d9c5116c7272bf88de'),
        (PlexObject, '_getAttrValue', _get_attr_value, 'df6e55a4e7b8c3cb6507ec7c4a1956a0b53a2be5ca7c97c7c2143fe715cc5095'),
        (PlexObject, '_buildDetailsKey', build_details_key, '521fd2274d5b6938c9a513c1481b132df4455f469c9c5fcdc01c5a1334e65e1f'),
        (PlexObject, '_buildItem', build_item, '6033a510bbb7b78c33beb5c6dd27a211b3e5871d04e96e33e6ca45e7c4bf5516'),
        (PlexObject, '_checkAttrs', _check_attrs, '63774f2c264f1625e060e8b781b0ce9ee1a8484aad032a48363212d012e78f0f'),
        (PlexObject, 'findItem', find_item, 'c2fa6874b80cb35964b874b7a20caca692446ad1f9d30d0c9c17b97fed346a54'),
        (PlexObject, 'findItems', find_items, '627cf7e635ea5ada35a1c8be2a593652bb9c470eee492053ad7c9bc162ffd665'),
        (PlexPartialObject, '__getattribute__', get_attribute, '95bff73e5305d24a886df2b5bfa83a5ad76f3a619304a23d52265dc1bf21a750')
    ]
    for cls, method_name, patched_method, patched_sha256 in perf_patches:
        method = getattr(cls, method_name)
        current_sha256 = sha256(getsource(method).encode('utf-8')).hexdigest()
        if current_sha256 != patched_sha256:
            fqmn = f'{cls.__module__}.{method.__qualname__}'
            warnings.warn(PatchedMethodChanged(fqmn, patched_sha256, current_sha256, skip_changed))
            if skip_changed:
                continue

        setattr(cls, method_name, patched_method)
        if method_name == '_loadData' and (data_attr_patch_func := data_attr_patches.get(cls)):
            data_attr_patch_func()
        # print(f'Patched {method.__qualname__}')

    # Warn about changes to functions whose use was replaced in the methods patched above, but are not directly
    # monkey-patched themselves
    util_perf_patches = [
        # cast -> cast_num, cast_bool
        ('plexapi.utils.cast', cast, '7496260439ef28694812e05949a2a516ae477ef60f643d48206d5f1cce2fa435'),
        # toDatetime -> to_datetime
        ('plexapi.utils.toDatetime', toDatetime, 'cb0e95730eefe4d328331c89ec764a751a93063e37ec83b8f3d0a9926bd3c711'),
    ]
    for fq_name, func, patched_sha256 in util_perf_patches:
        current_sha256 = sha256(getsource(func).encode('utf-8')).hexdigest()
        if current_sha256 != patched_sha256:
            warnings.warn(PatchedMethodChanged(fq_name, patched_sha256, current_sha256))

    # endregion


# region Util Functions


def to_datetime(value):
    if value is None:
        return value

    try:
        value = int(value)
    except ValueError:
        log.warning(f'Failed to parse {value=} as an epoch timestamp')
        return None

    try:
        return datetime.fromtimestamp(value)
    except (OSError, OverflowError, ValueError):
        try:
            return datetime.fromtimestamp(0) + timedelta(seconds=value)
        except OverflowError:
            log.warning(f'Failed to parse {value=} as an epoch timestamp')
            return None


def parse_date(value: str | None) -> datetime | None:
    if value is None:
        return value

    try:
        return datetime.strptime(value, '%Y-%m-%d')
    except ValueError:
        log.warning(f'Failed to parse {value=} as a date')
        return None


def cast_bool(value):
    if value is None:
        return value
    elif value in (1, True, '1', 'true'):
        return True
    elif value in (0, False, '0', 'false'):
        return False
    else:
        raise ValueError(value)


def cast_num(func, value):
    if value is not None:
        try:
            return func(value)
        except ValueError:
            return float('nan')
    return value


cast_int = partial(cast_num, int)
cast_float = partial(cast_num, float)


# endregion


# region PlexObject Method Patches


def build_item(self, elem, cls=None, initpath=None):
    """ Factory function to build objects based on registered PLEXOBJECTS. """
    # cls is specified, build the object and return
    if not initpath:
        initpath = self._initpath
    if cls is not None:
        return cls(self._server, elem, initpath, parent=self)
    # cls is not specified, try looking it up in PLEXOBJECTS
    get_attr = elem.attrib.get
    if etype := get_attr('streamType') or get_attr('tagType') or get_attr('type'):
        if initpath == '/status/sessions':
            suffix = '.session'
        elif initpath.startswith('/status/sessions/history'):
            suffix = '.history'
        else:
            suffix = ''

        ecls = getPlexObject(f'{elem.tag}.{etype}{suffix}', elem.tag)
    else:
        ecls = getPlexObject(elem.tag, elem.tag)

    if ecls:
        return ecls(self._server, elem, initpath, parent=self)

    raise UnknownType(f'Unknown library type <{elem.tag} type={etype!r}../>')


def _normalize_find_item_data(data, cls, rtag, kwargs):
    # filter on cls attrs if specified
    if cls:
        if cls.TAG and 'tag' not in kwargs:
            kwargs['etag'] = cls.TAG
        if cls.TYPE and 'type' not in kwargs:
            kwargs['type'] = cls.TYPE

    # rtag to iter on a specific root tag using breadth-first search
    if rtag:
        try:
            return next(iterXMLBFS(data, rtag))
        except StopIteration:
            return Element('Empty')

    return data


def _build_items(self, cls, data, initpath, kwargs):
    # loop through all data elements to find matches
    for elem in data:
        if ele_matches_filters(elem, **kwargs):
            try:
                yield build_item(self, elem, cls, initpath)
            except UnknownType:
                pass


def find_item(self, data, cls=None, initpath=None, rtag=None, **kwargs):
    """ Load the specified data to find and build the first items with the specified tag
        and attrs. See :func:`~plexapi.base.PlexObject.fetchItem` for more details
        on how this is used.
    """
    data = _normalize_find_item_data(data, cls, rtag, kwargs)
    return next(_build_items(self, cls, data, initpath, kwargs), None)


def find_items(self, data, cls=None, initpath=None, rtag=None, **kwargs):
    """ Load the specified data to find and build all items with the specified tag
        and attrs. See :func:`~plexapi.base.PlexObject.fetchItem` for more details
        on how this is used.
    """
    data = _normalize_find_item_data(data, cls, rtag, kwargs)
    if data.tag == 'MediaContainer':
        items = MediaContainer[cls](self._server, data, initpath=initpath)
        for item in _build_items(self, cls, data, initpath, kwargs):
            items.append(item)
        return items
    else:
        return list(_build_items(self, cls, data, initpath, kwargs))


# endregion


class PatchedMethodChanged(UserWarning):
    def __init__(self, method_name: str, old_hash: str, new_hash: str, skipping: bool = False):
        self.method_name = method_name
        self.old = old_hash
        self.new = new_hash
        self.skipping = skipping

    def __str__(self) -> str:
        if self.skipping:
            prefix = f'Skipping patch for {self.method_name} because'
        else:
            prefix = f'Patching {self.method_name} despite the fact that'
        old_ver, new_ver = PATCHED_VERSION, PLEX_API_VERSION
        lines = (
            f'{prefix} its source changed since the patch applied in music.plex.patches was written.',
            f'The patch written for plexapi {old_ver=} is outdated for {new_ver=}, which is currently installed.',
            f'View the diff here:\nhttps://github.com/pkkid/python-plexapi/compare/{old_ver}...{new_ver}',
            f'Method code hashes:\nold={self.old}\nnew={self.new}'
        )
        return '\n'.join(lines)


# region Descriptors


class PlexAttribute:
    __slots__ = ('key', 'name')

    def __init__(self, key: str = None):
        self.key = key

    def __set_name__(self, owner, name: str):
        self.name = name
        if self.key is None:
            self.key = name

    @classmethod
    def set_names(cls, plex_cls):
        # __set_name__ is only called by the interpreter automatically when the descriptors are added the normal way
        for name, attr in plex_cls.__dict__.items():
            if isinstance(attr, cls):
                attr.__set_name__(plex_cls, name)


_getattr = object.__getattribute__


class PlexDataAttribute(PlexAttribute):
    __slots__ = ('cast_func', 'default')

    def __init__(self, key: str = None, cast_func: Callable = None, default=_NotSet):
        super().__init__(key)
        self.cast_func = cast_func
        self.default = default

    def __get__(self, instance, owner):
        try:
            data = _getattr(instance, '_data')  # Skip the custom __getattribute__ method
        except AttributeError:  # instance is None
            return self

        if self.default is _NotSet:
            value = data.attrib.get(self.key)
        else:
            value = data.attrib.get(self.key, self.default)

        if value is not None and self.cast_func:
            value = self.cast_func(value)

        instance.__dict__[self.name] = value
        return value


class PlexItemsAttribute(PlexAttribute):
    # Replaces lines in _loadData similar to ``self.findItems(data, media.Guid)``
    __slots__ = ('media_cls',)

    def __init__(self, media_cls):
        super().__init__(None)
        self.media_cls = media_cls

    def __get__(self, instance, owner):
        try:
            data = _getattr(instance, '_data')  # Skip the custom __getattribute__ method
        except AttributeError:  # instance is None
            return self

        instance.__dict__[self.name] = items = find_items(instance, data, self.media_cls)
        return items


# endregion


# region Descriptor Patches


def patch_audio_data_attrs():
    Audio.listType = 'audio'
    Audio.addedAt = PlexDataAttribute(cast_func=to_datetime)
    Audio.art = PlexDataAttribute()
    Audio.artBlurHash = PlexDataAttribute()
    Audio.distance = PlexDataAttribute(cast_func=cast_float)
    Audio.fields = PlexItemsAttribute(Field)
    Audio.guid = PlexDataAttribute()
    Audio.index = PlexDataAttribute(cast_func=cast_int)
    Audio.key = PlexDataAttribute(default='')
    Audio.lastRatedAt = PlexDataAttribute(cast_func=to_datetime)
    Audio.lastViewedAt = PlexDataAttribute(cast_func=to_datetime)
    Audio.librarySectionID = PlexDataAttribute(cast_func=cast_int)
    Audio.librarySectionKey = PlexDataAttribute()
    Audio.librarySectionTitle = PlexDataAttribute()
    Audio.moods = PlexItemsAttribute(Mood)
    Audio.musicAnalysisVersion = PlexDataAttribute(cast_func=cast_int)
    Audio.ratingKey = PlexDataAttribute(cast_func=cast_int)
    Audio.summary = PlexDataAttribute()
    Audio.thumb = PlexDataAttribute()
    Audio.thumbBlurHash = PlexDataAttribute()
    Audio.title = PlexDataAttribute()
    Audio.type = PlexDataAttribute()
    Audio.updatedAt = PlexDataAttribute(cast_func=to_datetime)
    Audio.userRating = PlexDataAttribute(cast_func=cast_float, default=0)
    Audio.viewCount = PlexDataAttribute(cast_func=cast_int, default=0)

    PlexAttribute.set_names(Audio)

    def title_sort(self: Audio):
        return self._data.attrib.get('titleSort', self.title)

    Audio.titleSort = property(title_sort)


def patch_playable_data_attrs():
    Playable.playlistItemID = PlexDataAttribute(cast_func=cast_int)  # playlist
    Playable.playQueueItemID = PlexDataAttribute(cast_func=cast_int)  # playqueue

    PlexAttribute.set_names(Playable)


def patch_track_data_attrs():
    Track.audienceRating = PlexDataAttribute(cast_func=cast_float)
    Track.chapters = PlexItemsAttribute(Chapter)
    Track.chapterSource = PlexDataAttribute()
    Track.collections = PlexItemsAttribute(Collection)
    Track.duration = PlexDataAttribute(cast_func=cast_int)
    Track.genres = PlexItemsAttribute(Genre)
    Track.grandparentArt = PlexDataAttribute()
    Track.grandparentGuid = PlexDataAttribute()
    Track.grandparentKey = PlexDataAttribute()
    Track.grandparentRatingKey = PlexDataAttribute(cast_func=cast_int)
    Track.grandparentTheme = PlexDataAttribute()
    Track.grandparentThumb = PlexDataAttribute()
    Track.grandparentTitle = PlexDataAttribute()
    Track.guids = PlexItemsAttribute(Guid)
    Track.labels = PlexItemsAttribute(Label)
    Track.media = PlexItemsAttribute(Media)
    Track.originalTitle = PlexDataAttribute()
    Track.parentGuid = PlexDataAttribute()
    Track.parentIndex = PlexDataAttribute()
    Track.parentKey = PlexDataAttribute()
    Track.parentRatingKey = PlexDataAttribute(cast_func=cast_int)
    Track.parentThumb = PlexDataAttribute()
    Track.parentTitle = PlexDataAttribute()
    Track.primaryExtraKey = PlexDataAttribute()
    Track.rating = PlexDataAttribute(cast_func=cast_float)
    Track.ratingCount = PlexDataAttribute(cast_func=cast_int)
    Track.skipCount = PlexDataAttribute(cast_func=cast_int)
    Track.sourceURI = PlexDataAttribute('source')  # remote playlist item
    Track.viewOffset = PlexDataAttribute(cast_func=cast_int, default=0)
    Track.year = PlexDataAttribute(cast_func=cast_int)

    PlexAttribute.set_names(Track)


def patch_album_data_attrs():
    Album.audienceRating = PlexDataAttribute(cast_func=cast_float)
    Album.collections = PlexItemsAttribute(Collection)
    Album.formats = PlexItemsAttribute(Format)
    Album.genres = PlexItemsAttribute(Genre)
    Album.guids = PlexItemsAttribute(Guid)
    # Album.key: Handled in album_load_data
    Album.labels = PlexItemsAttribute(Label)
    Album.leafCount = PlexDataAttribute(cast_func=cast_int)
    Album.loudnessAnalysisVersion = PlexDataAttribute(cast_func=cast_int)
    Album.originallyAvailableAt = PlexDataAttribute(cast_func=parse_date)
    Album.parentGuid = PlexDataAttribute()
    Album.parentKey = PlexDataAttribute()
    Album.parentRatingKey = PlexDataAttribute(cast_func=cast_int)
    Album.parentTheme = PlexDataAttribute()
    Album.parentThumb = PlexDataAttribute()
    Album.parentTitle = PlexDataAttribute()
    Album.rating = PlexDataAttribute(cast_func=cast_float)
    Album.studio = PlexDataAttribute()
    Album.styles = PlexItemsAttribute(Style)
    Album.subformats = PlexItemsAttribute(Subformat)
    Album.viewedLeafCount = PlexDataAttribute(cast_func=cast_int)
    Album.year = PlexDataAttribute(cast_func=cast_int)

    PlexAttribute.set_names(Album)


def patch_artist_data_attrs():
    Artist.albumSort = PlexDataAttribute(cast_func=cast_int, default='-1')
    Artist.audienceRating = PlexDataAttribute(cast_func=cast_float)
    Artist.collections = PlexItemsAttribute(Collection)
    Artist.countries = PlexItemsAttribute(Country)
    Artist.genres = PlexItemsAttribute(Genre)
    Artist.guids = PlexItemsAttribute(Guid)
    # Artist.key: handled in artist_load_data
    Artist.labels = PlexItemsAttribute(Label)
    # Artist.locations: handled in artist_load_data
    Artist.rating = PlexDataAttribute(cast_func=cast_float)
    Artist.similar = PlexItemsAttribute(Similar)
    Artist.styles = PlexItemsAttribute(Style)
    Artist.theme = PlexDataAttribute()

    PlexAttribute.set_names(Artist)


# endregion
