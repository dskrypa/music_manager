"""
Patches for PlexAPI

:author: Doug Skrypa
"""

import logging
import warnings
from datetime import datetime
from functools import cached_property
from hashlib import sha256
from inspect import getsource
from urllib.parse import urlencode
from xml.etree.ElementTree import Element

from plexapi.audio import Track, Album, Artist, Audio
from plexapi.base import PlexObject, Playable, PlexPartialObject
from plexapi.base import _DONT_RELOAD_FOR_KEYS, _DONT_OVERWRITE_SESSION_KEYS, USER_DONT_RELOAD_FOR_KEYS
from plexapi.exceptions import UnknownType
from plexapi.media import Media, Field, Mood, Collection, Label
from plexapi.utils import PLEXOBJECTS, toDatetime, cast, iterXMLBFS

from ..common.ratings import stars
from ..common.utils import deinit_colorama as _deinit_colorama
from .filters import get_attr_operator, get_attr_value, check_attrs

__all__ = ['apply_plex_patches']
log = logging.getLogger(__name__)

_APPLIED_BASIC_PATCHES = False
_APPLIED_PERF_PATCHES = False


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
    def album_repr(self):
        fmt = '<{}#{}[{}]({!r}, artist={!r}, genres={})>'
        rating = stars(float(self._data.attrib.get('userRating', 0)))
        genres = ', '.join(g.tag for g in self.genres)
        return fmt.format(self.__class__.__name__, self._int_key, rating, self.title, self.parentTitle, genres)

    def artist_repr(self):
        fmt = '<{}#{}[{}]({!r}, genres={})>'
        rating = stars(float(self._data.attrib.get('userRating', 0)))
        genres = ', '.join(g.tag for g in self.genres)
        return fmt.format(self.__class__.__name__, self._int_key, rating, self.title, genres)

    def track_repr(self, rating=None):
        fmt = '<{}#{}[{}]({!r}, artist={!r}, album={!r})>'
        rating = stars(rating or self.userRating or 0)
        artist = self.originalTitle if self.grandparentTitle == 'Various Artists' else self.grandparentTitle
        return fmt.format(self.__class__.__name__, self._int_key, rating, self.title, artist, self.parentTitle)

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
    # region Utility Patches

    def to_datetime(value):
        if value is not None:
            value = int(value)
            if value <= 0:
                value = 86400
            value = datetime.fromtimestamp(value)
        return value

    def cast_num(func, value):
        if value is not None:
            try:
                return func(value)
            except ValueError:
                return float('nan')
        return value

    # endregion

    # region Method Patches

    def audio_load_data(self: Track, data: Element):
        """ Load attribute values from Plex XML response. """
        self._data = data
        get_attrib = data.attrib.get
        self.addedAt = to_datetime(get_attrib('addedAt'))
        self.art = get_attrib('art')
        self.artBlurHash = get_attrib('artBlurHash')
        # self.fields = self.findItems(data, Field)
        self.fields = find_items(self, data, Field)
        self.guid = get_attrib('guid')
        self.index = cast_num(int, get_attrib('index'))
        self.key = get_attrib('key', '')
        self.lastRatedAt = to_datetime(get_attrib('lastRatedAt'))
        self.lastViewedAt = to_datetime(get_attrib('lastViewedAt'))
        self.librarySectionID = cast_num(int, get_attrib('librarySectionID'))
        self.librarySectionKey = get_attrib('librarySectionKey')
        self.librarySectionTitle = get_attrib('librarySectionTitle')
        self.listType = 'audio'
        # self.moods = self.findItems(data, Mood)
        self.moods = find_items(self, data, Mood)
        self.musicAnalysisVersion = cast_num(int, get_attrib('musicAnalysisVersion'))
        self.ratingKey = cast_num(int, get_attrib('ratingKey'))
        self.summary = get_attrib('summary')
        self.thumb = get_attrib('thumb')
        self.thumbBlurHash = get_attrib('thumbBlurHash')
        self.title = get_attrib('title')
        self.titleSort = get_attrib('titleSort', self.title)
        self.type = get_attrib('type')
        self.updatedAt = to_datetime(get_attrib('updatedAt'))
        self.userRating = cast_num(float, get_attrib('userRating', 0))
        self.viewCount = cast_num(int, get_attrib('viewCount', 0))

    def playable_load_data(self: Track, data: Element):
        get_attrib = data.attrib.get
        self.sessionKey = cast_num(int, get_attrib('sessionKey'))  # session
        self.usernames = self.listAttrs(data, 'title', etag='User')  # session
        # self.players = self.findItems(data, etag='Player')  # session
        self.players = find_items(self, data, etag='Player')
        # self.transcodeSessions = self.findItems(data, etag='TranscodeSession')  # session
        self.transcodeSessions = find_items(self, data, etag='TranscodeSession')
        # self.session = self.findItems(data, etag='Session')  # session
        self.session = find_items(self, data, etag='Session')
        self.viewedAt = to_datetime(get_attrib('viewedAt'))  # history
        self.accountID = cast_num(int, get_attrib('accountID'))  # history
        self.deviceID = cast_num(int, get_attrib('deviceID'))  # history
        self.playlistItemID = cast_num(int, get_attrib('playlistItemID'))  # playlist
        self.playQueueItemID = cast_num(int, get_attrib('playQueueItemID'))  # playqueue

    def track_load_data(self: Track, data: Element):
        """ Load attribute values from Plex XML response. """
        audio_load_data(self, data)
        playable_load_data(self, data)
        get_attrib = data.attrib.get
        self.chapterSource = get_attrib('chapterSource')
        # self.collections = self.findItems(data, media.Collection)
        self.collections = find_items(self, data, Collection)
        self.duration = cast_num(int, get_attrib('duration'))
        self.grandparentArt = get_attrib('grandparentArt')
        self.grandparentGuid = get_attrib('grandparentGuid')
        self.grandparentKey = get_attrib('grandparentKey')
        self.grandparentRatingKey = cast_num(int, get_attrib('grandparentRatingKey'))
        self.grandparentTheme = get_attrib('grandparentTheme')
        self.grandparentThumb = get_attrib('grandparentThumb')
        self.grandparentTitle = get_attrib('grandparentTitle')
        self.labels = find_items(self, data, Label)
        # self.media = self.findItems(data, Media)
        self.media = find_items(self, data, Media)
        self.originalTitle = get_attrib('originalTitle')
        self.parentGuid = get_attrib('parentGuid')
        self.parentIndex = get_attrib('parentIndex')
        self.parentKey = get_attrib('parentKey')
        self.parentRatingKey = cast_num(int, get_attrib('parentRatingKey'))
        self.parentThumb = get_attrib('parentThumb')
        self.parentTitle = get_attrib('parentTitle')
        self.primaryExtraKey = get_attrib('primaryExtraKey')
        self.ratingCount = cast_num(int, get_attrib('ratingCount'))
        self.skipCount = cast_num(int, get_attrib('skipCount'))
        self.viewOffset = cast_num(int, get_attrib('viewOffset', 0))
        self.year = cast_num(int, get_attrib('year'))

    _get_attr_operator = staticmethod(get_attr_operator)
    _get_attr_value = staticmethod(get_attr_value)
    _check_attrs = staticmethod(check_attrs)

    false = {False, 0, '0'}

    def build_details_key(self, **kwargs):
        """ Builds the details key with the XML include parameters.
            All parameters are included by default with the option to override each parameter
            or disable each parameter individually by setting it to False or 0.
        """
        details_key = self.key
        try:
            if details_key and (cls_includes := self._INCLUDES):
                if kwargs:
                    includes = {}
                    for k, v in cls_includes.items():
                        value = kwargs.get(k, v)
                        if value not in false:
                            includes[k] = 1 if value is True else value
                else:
                    # includes = {k: 1 if v is True else v for k, v in cls_includes.items() if v not in false}
                    includes = cls_includes
                if includes:
                    details_key += '?' + urlencode(sorted(includes.items()))
        except AttributeError:
            pass
        return details_key

    def build_item(self, elem, cls=None, initpath=None):
        """ Factory function to build objects based on registered PLEXOBJECTS. """
        # cls is specified, build the object and return
        initpath = initpath or self._initpath
        if cls is not None:
            return cls(self._server, elem, initpath, parent=self)
        # cls is not specified, try looking it up in PLEXOBJECTS
        get_ecls = PLEXOBJECTS.get
        get_attr = elem.attrib.get
        if etype := get_attr('streamType') or get_attr('tagType') or get_attr('type'):
            ecls = get_ecls(f'{elem.tag}.{etype}') or get_ecls(elem.tag)
        else:
            ecls = get_ecls(elem.tag)
        if ecls:
            return ecls(self._server, elem, initpath)
        raise UnknownType(f'Unknown library type <{elem.tag} type={etype!r}../>')

    def find_items(self, data, cls=None, initpath=None, rtag=None, **kwargs):
        """ Load the specified data to find and build all items with the specified tag
            and attrs. See :func:`~plexapi.base.PlexObject.fetchItem` for more details
            on how this is used.
        """
        # filter on cls attrs if specified
        if cls and cls.TAG and 'tag' not in kwargs:
            kwargs['etag'] = cls.TAG
        if cls and cls.TYPE and 'type' not in kwargs:
            kwargs['type'] = cls.TYPE
        # rtag to iter on a specific root tag using breadth-first search
        if rtag:
            data = next(iterXMLBFS(data, rtag), [])  # Newish in 4.11.2
            # data = next(data.iter(rtag), [])  # Prior to 4.11.2
        # loop through all data elements to find matches
        items = []
        for elem in data:
            if check_attrs(elem, **kwargs):
                try:
                    items.append(build_item(self, elem, cls, initpath))
                except UnknownType:
                    pass
        return items

    no_reload = _DONT_RELOAD_FOR_KEYS.union(_DONT_OVERWRITE_SESSION_KEYS).union(USER_DONT_RELOAD_FOR_KEYS)

    real_get_attribute = object.__getattribute__

    def get_attribute(self: PlexPartialObject, attr: str):
        # Dragons inside.. :-/
        value = real_get_attribute(self, attr)
        # Check a few cases where we don't want to reload
        if attr in no_reload or attr.startswith('_') or value not in (None, []):
            return value
        elif not self.key or (self._details_key or self.key) == self._initpath:  # == self.isFullObject()
            return value
        elif not self._autoReload:
            return value
        # Log the reload.
        title = self.__dict__.get('title') or self.__dict__.get('name')
        obj_name = f'{self.__class__.__name__} {title!r}' if title else self.__class__.__name__
        log.debug(f'Reloading {obj_name} for attr {attr!r}')
        # Reload and return the value
        self._reload(_overwriteNone=False)
        return real_get_attribute(self, attr)

    # endregion

    # region Patch Target Change Checks

    # Last updated for PlexAPI version: 4.11.2 (2022-06-19)
    perf_patches = [
        (Track, '_loadData', track_load_data, '8490896099e50c5a8d4b0edd9a3d45e0139711dc24bc159e63646fa1b5831006'),
        (Audio, '_loadData', audio_load_data, '582a5d25a9fa824c426c0b7c1f011a7297a6211ec6d06d092b8909482cee1dbd'),
        (Playable, '_loadData', playable_load_data, 'd63b79f5999d3a6fd9deb5e959f3da6e9621705f329183984993477da57a05b8'),
        (PlexObject, '_getAttrOperator', _get_attr_operator, '401006c3c6dd54f2017d5c224a5b1f8ccba9320c37d4eac00dfe8ddcea7ca760'),
        (PlexObject, '_getAttrValue', _get_attr_value, '2aa52b5a750f2bafab3ff195d9def179401e4f5e4cca53eac40c055aedc6db22'),
        (PlexObject, '_buildDetailsKey', build_details_key, 'f71b5ac061a50d27fa22ba28c7a5c3abe709222b0a9bb79b8cd526defa9508fe'),
        (PlexObject, '_checkAttrs', _check_attrs, '63774f2c264f1625e060e8b781b0ce9ee1a8484aad032a48363212d012e78f0f'),
        (PlexObject, '_buildItem', build_item, '6a50c92924fcf8a65c77514e8076440019e5b114b6b04da9c6093367f545da6d'),
        (PlexObject, 'findItems', find_items, '72eefd6656c8cdc26bc9e2a50c720ae682dfac083c926c79b4cbbfea140861e3'),
        (PlexPartialObject, '__getattribute__', get_attribute, '56810ca596786f37b2fd2240f2fa97a7ee2d0539e2838168cf98cc936be5c4a9')
    ]
    for cls, method_name, patched_method, patched_sha256 in perf_patches:
        method = getattr(cls, method_name)
        current_sha256 = sha256(getsource(method).encode('utf-8')).hexdigest()
        if current_sha256 != patched_sha256:
            warnings.warn(PatchedMethodChanged(method.__qualname__, patched_sha256, current_sha256))
            if skip_changed:
                continue

        setattr(cls, method_name, patched_method)
        # print(f'Patched {method.__qualname__}')

    util_perf_patches = [
        ('plexapi.utils.cast', cast, cast_num, 'a786e4c543ed60802e066de7c2b469d71096ff9236cf21c6d33c459f6a6ffeb4'),
        ('plexapi.utils.toDatetime', toDatetime, to_datetime, '56cfa4cc2ec8ca95a0eedf93ed558fbab2ef2370c75249b1c624902343fed414'),
    ]
    for fq_name, func, patched_func, patched_sha256 in util_perf_patches:
        current_sha256 = sha256(getsource(func).encode('utf-8')).hexdigest()
        if current_sha256 != patched_sha256:
            warnings.warn(PatchedMethodChanged(fq_name, patched_sha256, current_sha256))

    # endregion


class PatchedMethodChanged(UserWarning):
    def __init__(self, method_name: str, old_hash: str, new_hash: str):
        self.method_name = method_name
        self.old = old_hash
        self.new = new_hash

    def __str__(self) -> str:
        return (
            f'The source for {self.method_name} changed since the patch applied in music.plex.patches was written:'
            f'\nold={self.old}\nnew={self.new}'
        )
