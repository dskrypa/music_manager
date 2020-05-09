"""
:author: Doug Skrypa
"""

import json
import logging
import re
import string
import traceback
from collections import defaultdict, OrderedDict
from contextlib import suppress
from itertools import chain
from pathlib import Path
from urllib.parse import urlparse

import bs4
from cachetools import LRUCache

from ds_tools.caching import cached, DictAttrProperty
from ds_tools.compat import cached_property
from ds_tools.http import CodeBasedRestException
from ds_tools.unicode import LangCat, romanized_permutations, matches_permutation
from ds_tools.utils import normalize_roman_numerals, ParentheticalParser
from ds_tools.utils.soup import soupify
from ..name_processing import eng_cjk_sort, fuzz_process, parse_name, revised_weighted_ratio, split_name
from .exceptions import *
from .utils import (
    comparison_type_check, edition_combinations, get_page_category, multi_lang_name, sanitize_path, strify_collabs
)
from .rest import WikiClient, KindieWikiClient, KpopWikiClient, WikipediaClient, DramaWikiClient
from .parsing import *

__all__ = [
    'find_ost', 'WikiAgency', 'WikiAlbum', 'WikiArtist', 'WikiDiscography', 'WikiEntity', 'WikiEntityMeta',
    'WikiFeatureOrSingle', 'WikiGroup', 'WikiSinger', 'WikiSongCollection', 'WikiSongCollectionPart', 'WikiSoundtrack',
    'WikiTrack', 'WikiTVSeries', 'WikiMatchable', 'WikiPersonCollection', 'WikiCompetitionOrShow'
]
log = logging.getLogger(__name__)
logr = {'scoring': logging.getLogger(__name__ + '.scoring')}
for logger in logr.values():
    logger.setLevel(logging.WARNING)

ALBUM_DATED_TYPES = ('Single', 'Soundtrack', 'Collaboration', 'Extended Play')
ALBUM_MULTI_DISK_TYPES = ('Albums', 'Special Albums', 'Japanese Albums', 'Remake Albums', 'Repackage Albums')
ALBUM_NUMBERED_TYPES = ('Album', 'Mini Album', 'Special Album', 'Single Album', 'Remake Album', 'Repackage Album')
DISCOGRAPHY_TYPE_MAP = {
    'best_albums': 'Compilation',
    'collaborations': 'Collaboration',
    'collaborations_and_features': 'Collaboration',
    'collaboration_singles': 'Collaboration',
    'digital_singles': 'Single',
    'eps': 'Extended Play',
    'extended_plays': 'Extended Play',
    'features': 'Collaboration',
    'live_albums': 'Live',
    'mini_albums': 'Mini Album',
    'mixtapes': 'Mixtape',
    'osts': 'Soundtrack',
    'other_releases': 'Single',
    'promotional_singles': 'Single',
    'remake_albums': 'Remake Album',    # Album that contains only covers of other artists' songs
    'repackage_albums': 'Album',
    'single_albums': 'Single Album',
    'singles': 'Single',
    'special_albums': 'Special Album',
    'special_singles': 'Single',
    'studio_albums': 'Album'
}
SINGLE_TYPE_TO_BASE_TYPE = {
    None: 'singles',
    'as lead artist': 'singles',
    'as a lead artist': 'singles',
    'collaborations': 'collaborations',
    'as featured artist': 'features',
    'other releases': 'singles',
    'promotional singles': 'singles'
}
JUNK_CHARS = string.whitespace + string.punctuation
NUM_STRIP_TBL = str.maketrans({c: '' for c in '0123456789'})
NUMS = {
    'first': '1st', 'second': '2nd', 'third': '3rd', 'fourth': '4th', 'fifth': '5th', 'sixth': '6th',
    'seventh': '7th', 'eighth': '8th', 'ninth': '9th', 'tenth': '10th', 'debut': '1st'
}
ROMAN_NUMERALS = {'I': 1, 'II': 2, 'III': 3, 'IV': 4, 'V': 5, 'VI': 6, 'VII': 7, 'VIII': 8, 'IX': 9, 'X': 10}
STRIP_TBL = str.maketrans({c: '' for c in JUNK_CHARS})


class WikiEntityMeta(type):
    _category_classes = {}
    _category_bases = defaultdict(set)
    _instances = {}

    def __init__(cls, name, bases, attr_dict):
        with suppress(AttributeError):
            # noinspection PyUnresolvedReferences
            category = cls._category
            if category is None or isinstance(category, str):
                WikiEntityMeta._category_classes[category] = cls
            else:
                for cat in category:
                    WikiEntityMeta._category_bases[cat].add(cls)

        super().__init__(name, bases, attr_dict)

    def __call__(
        cls, uri_path=None, client=None, *, name=None, disco_entry=None, no_type_check=False, no_fetch=False,
        of_group=None, aliases=None, **kwargs
    ):
        """
        :param str|None uri_path: The uri path for a page on a wiki
        :param WikiClient|None client: The WikiClient object to use to retrieve the wiki page
        :param str|None name: The name of a WikiEntity to lookup if the uri_path is unknown
        :param dict|None disco_entry: A dict containing information about an album from an Artist's discography section
        :param bool no_type_check: Skip type checks and do not cache the returned object
        :param bool no_fetch: Skip page retrieval
        :param str|WikiGroup of_group: Group that the given name is associated with as a member or sub-unit, or as an
          associated act
        :param aliases: Known aliases for the entity.  If no name or uri_path is provided, the first alias will be
          considered instead.  If a disambiguation page is returned, then aliases help to find the correct match.
        :param kwargs: Additional keyword arguments to pass to the WikiEntity when initializing it
        :return WikiEntity: A WikiEntity (or subclass thereof) based on the provided information
        """
        orig_client = client
        # noinspection PyUnresolvedReferences
        cls_cat = cls._category
        lang = disco_entry.get('language') if disco_entry else None
        alias_srcs = (name, aliases, disco_entry.get('title') if disco_entry and not no_fetch else None)
        _all_aliases = chain.from_iterable((a,) if isinstance(a, str) else a for a in alias_srcs if a)
        name_aliases = tuple(filter(None, _all_aliases))
        # log.debug('cls({!r}, name={!r}, aliases={!r}): name_aliases={!r}'.format(uri_path, name, aliases, name_aliases))
        if not name_aliases and not uri_path:
            raise WikiEntityIdentificationException('A uri_path or name/aliases is required')

        if not no_fetch:
            if disco_entry:
                uri_path = uri_path or disco_entry.get('uri_path')
                disco_site = disco_entry.get('wiki')
                if disco_site and not client:
                    client = WikiClient.for_site(disco_site)
                # elif disco_site and client._site != disco_site:   # Have not seen a need for this yet
                #     fmt = 'Changing client for uri_path={!r} from {} because it has disco_site={!r} specified'
                #     log.log(9, fmt.format(uri_path, client, disco_site))
                #     client = WikiClient.for_site(disco_site)
            elif name_aliases and not uri_path:
                client = client or KpopWikiClient()
                if of_group and not isinstance(of_group, WikiGroup):
                    try:
                        of_group = WikiGroup(aliases=of_group)
                    except WikiTypeError as e:
                        fmt = 'Error initializing WikiGroup(aliases={!r}) for {}(aliases={!r}): {}'
                        log.log(9, fmt.format(of_group, cls.__name__, name_aliases, e))
                    except Exception as e:
                        fmt = 'Error initializing WikiGroup(aliases={!r}) for {}(aliases={!r}): {}'
                        log.debug(fmt.format(of_group, cls.__name__, name_aliases, e))

                if of_group and isinstance(of_group, WikiGroup):
                    return of_group.find_associated(name_aliases)

                key = (uri_path, client, name_aliases, lang)
                obj = WikiEntityMeta._get_match(cls, key, client, cls_cat)  # Does a type check
                if obj is not None:
                    return obj
                elif all(LangCat.contains_any_not(n, LangCat.ENG) for n in name_aliases):
                    if orig_client is None or isinstance(client, KpopWikiClient):
                        clients = (client, KindieWikiClient())
                    else:
                        clients = (client,)
                    return WikiEntityMeta._create_via_search(cls, key, name_aliases, *clients)
                else:
                    exc = None
                    for i, name in enumerate(name_aliases):
                        try:
                            # log.debug('{}: Attempting to normalize {!r}'.format(client, name))
                            uri_path = client.normalize_name(name)
                        except AmbiguousEntityException as e:
                            if e.alternatives:
                                return e.find_matching_alternative(cls, name_aliases, associated_with=of_group)
                            if len(name_aliases) > 1 and i < len(name_aliases):
                                return WikiEntityMeta._create_via_search(cls, key, name_aliases, client)
                        except CodeBasedRestException as e:
                            if e.code == 404:
                                if any(LangCat.contains_any_not(n, LangCat.ENG) for n in name_aliases):
                                    clients = tuple() if orig_client is None else (client,)
                                    # Only needs to run once - uses all name aliases
                                    return WikiEntityMeta._create_via_search(cls, key, name_aliases, *clients)
                                elif orig_client is None:
                                    try:
                                        client = KindieWikiClient()
                                        uri_path = client.normalize_name(name)
                                    except CodeBasedRestException:
                                        client = WikipediaClient()
                                        try:
                                            uri_path = client.normalize_name(name)
                                        except CodeBasedRestException:
                                            fmt = 'Unable to find a page that matches aliases={!r} from any site: {}'
                                            exc = NoUrlFoundException(fmt.format(name_aliases, e))

                            if not uri_path and not exc:
                                exc = e
                        finally:
                            if uri_path:
                                break

                    if not uri_path:
                        if exc:
                            raise exc
                        else:
                            raise NoUrlFoundException('Unable to find a uri_path for {!r}'.format(name_aliases))

            if uri_path and uri_path.startswith(('http://', 'https://', '//')):
                _url = urlparse(uri_path)   # Note: // => alternate subdomain of fandom.com
                if client:
                    fmt = 'Changing client for uri_path={!r} from {} because it is using a different domain'
                    log.log(9, fmt.format(uri_path, client))
                try:
                    client = WikiClient.for_site(_url.hostname)
                except Exception as e:
                    raise InvalidWikiClientException('No client configured for {}'.format(_url.hostname)) from e
                uri_path = _url.path[6:] if _url.path.startswith('/wiki/') else _url.path
            elif client is None:
                client = KpopWikiClient()

        if no_type_check or no_fetch:
            # fmt = 'Initializing with no fetch/type_check: {}({!r}, {}, name={!r})'
            # log.debug(fmt.format(cls.__name__, uri_path, client, name))
            obj = cls.__new__(cls, uri_path, client)
            # noinspection PyArgumentList
            obj.__init__(uri_path, client, name=name_aliases, disco_entry=disco_entry, no_fetch=no_fetch, **kwargs)
            # noinspection PyUnresolvedReferences
            obj._post_init()
            return obj

        is_feat_collab = disco_entry and disco_entry.get('base_type') in ('features', 'collaborations', 'singles')
        if uri_path or is_feat_collab:
            uri_path = client.normalize_name(uri_path) if uri_path and ' ' in uri_path else uri_path
            key = (uri_path, client, name_aliases, lang)
            obj = WikiEntityMeta._get_match(cls, key, client, cls_cat)
            if obj is not None:
                return obj
            elif not uri_path and is_feat_collab:
                category, url, raw = 'collab/feature/single', None, None
            else:
                url = client.url_for(uri_path)
                # Note: client.get_entity_base caches args->return vals
                raw, cats = client.get_entity_base(uri_path, cls_cat.title() if isinstance(cls_cat, str) else None)
                category = get_page_category(url, cats, raw=raw)

            # noinspection PyTypeChecker
            WikiEntityMeta._check_type(cls, url, category, cls_cat, raw)
            exp_cls = WikiEntityMeta._category_classes.get(category)
        else:
            exp_cls = cls
            raw = None
            key = (uri_path, client, name_aliases, lang)

        if key not in WikiEntityMeta._instances:
            obj = exp_cls.__new__(exp_cls, uri_path, client)
            # noinspection PyArgumentList
            obj.__init__(uri_path, client, name=name_aliases, raw=raw, disco_entry=disco_entry, **kwargs)
            WikiEntityMeta._instances[key] = obj
            # noinspection PyUnresolvedReferences
            obj._post_init()
            # log.debug('{}: Storing in instance cache with key={}'.format(obj, key), extra={'color': 14})
        else:
            obj = WikiEntityMeta._instances[key]
            # log.debug('{}: Found in instance cache with key={}'.format(obj, key), extra={'color': 10})

        if of_group:
            if isinstance(obj, WikiSinger):
                if obj.member_of is None or not obj.member_of.matches(of_group):
                    if obj.find_associated(of_group):
                        return obj
                    fmt = 'Found {} for uri_path={!r}, aliases={!r}, but they are a member_of={}, not of_group={!r}'
                    msg = fmt.format(obj, uri_path, name_aliases, obj.member_of, of_group)
                    raise WikiEntityIdentificationException(msg)
            elif isinstance(obj, WikiGroup):
                if obj.subunit_of is None or not obj.subunit_of.matches(of_group):
                    if obj.find_associated(of_group):
                        return obj
                    fmt = 'Found {} for uri_path={!r}, aliases={!r}, but they are a subunit_of={}, not of_group={!r}'
                    msg = fmt.format(obj, uri_path, name_aliases, obj.subunit_of, of_group)
                    raise WikiEntityIdentificationException(msg)
            else:
                raise WikiTypeError('{} is a {}, so cannot be of_group={}'.format(obj, type(obj).__name__, of_group))

        return obj

    @staticmethod
    def _create_via_search(cls, key, name_aliases, *clients, separate=False):
        clients = clients or (KpopWikiClient(), KindieWikiClient(), WikipediaClient())
        dbg_fmt = 'Search of {} for {!r} yielded non-match: {}'
        # Check 1st 3 results from each site for non-eng name
        for client in clients:
            log.debug('Attempting search of {} for: {!r}'.format(client._site, '|'.join(name_aliases)))
            if separate:    # fandom.com's search engine does NOT support any type of OR operator
                results = list(chain.from_iterable(client.search(a)[:3] for a in name_aliases[:3]))
            else:
                results = client.search('|'.join(name_aliases))[:3]
            # log.debug('Results from {} [separate={}]: {}'.format(client._site, separate, results))
            for i, (link_text, link_href) in enumerate(results):
                # log.debug('{} result {}: {!r}={}'.format(client._site, i, link_text, link_href))
                try:
                    entity = cls(link_href, client=client)
                except WikiTypeError as e:
                    log.log(9, dbg_fmt.format(client.host, name_aliases, e))
                else:
                    if entity.matches(name_aliases):
                        WikiEntityMeta._instances[key] = entity
                        WikiEntityMeta._instances[(link_href, client, name_aliases)] = entity
                        return entity
                    else:
                        log.log(9, dbg_fmt.format(client.host, name_aliases, entity))
        else:
            if separate:
                raise WikiEntityIdentificationException('No matches found for {!r} via search'.format(name_aliases))
            return WikiEntityMeta._create_via_search(cls, key, name_aliases, *clients, separate=True)

    @staticmethod
    def _get_match(cls, key, client, cls_cat):
        if key in WikiEntityMeta._instances:
            inst = WikiEntityMeta._instances[key]
            if cls_cat and ((inst._category == cls_cat) or (inst._category in cls_cat)):
                return inst
            else:
                url = client.url_for(inst._uri_path) if inst._uri_path is not None else None
                WikiEntityMeta._check_type(cls, url, inst._category, cls_cat, inst._raw)
        return None

    @staticmethod
    def _check_type(cls, url, category, cls_cat, raw):
        if category == 'disambiguation':
            raise AmbiguousEntityException(url, raw)

        exp_cls = WikiEntityMeta._category_classes.get(category)
        exp_bases = WikiEntityMeta._category_bases[category]
        has_unexpected_cls = exp_cls and not issubclass(exp_cls, cls) and cls._category is not None
        has_unexpected_base = exp_bases and not any(issubclass(cls, b) for b in exp_bases) and cls._category is not None
        if has_unexpected_cls or has_unexpected_base or (exp_cls is None and not exp_bases):
            article = 'an' if category and category[0] in 'aeiou' else 'a'
            # exp_cls_strs = (getattr(exp_cls, '__name__', None), getattr(exp_base, '__name__', None))
            # log.debug('Specified cls={}, exp_cls={}, exp_base={}'.format(cls.__name__, *exp_cls_strs))
            raise WikiTypeError(url, article, category, cls_cat, cls)


class WikiMatchable:
    _category = None
    __cache = LRUCache(500)
    _int_pat = re.compile(r'\d+')
    __part_pat = re.compile(r'^(.*)part \d+$', re.IGNORECASE)
    __abbrev_pat = re.compile(r'\.(?!\s)')
    __lang_ver_pat = re.compile(r'(.*)[(-](\w+) (?:ver\.?|version)[)-]$', re.IGNORECASE)

    def __init__(self):
        self._strip_special = False
        self._num_cache = {}
        self._match_cache = LRUCache(100)

    @classmethod
    def __cached(cls, obj, strip_special=False, track=None):
        try:
            return cls.__cache[obj]
        except (KeyError, TypeError):
            # log.debug('Cache miss for {!r}'.format(obj), extra={'color': (1, 14)})
            m = WikiMatchable()
            m._obj = obj
            m._strip_special = strip_special
            m._track = track
            try:
                cls.__cache[obj] = m
            except TypeError:
                pass
            return m

    @classmethod
    def score_simple(cls, a, b):
        return cls.__cached(a).score_match(b)

    def update_name(self, eng_name, cjk_name, update_others=True):
        # fmt = '{}: Updating eng={!r}=>{!r}, cjk={!r}=>{!r}'
        # log.info(fmt.format(self, self.english_name, eng_name, self.cjk_name, cjk_name), extra={'color': 'red'})
        self.english_name = normalize_roman_numerals(eng_name) if eng_name else self.english_name
        self.cjk_name = normalize_roman_numerals(cjk_name) if cjk_name else self.cjk_name
        self.name = multi_lang_name(self.english_name, self.cjk_name)
        try:
            del self.__dict__['aliases']
        except KeyError:
            pass

        if update_others and isinstance(self, WikiTrack):
            for track in self.collection.get_tracks():
                if track is not self:
                    eng_and_no_cjk = track.english_name == self.english_name and not track.cjk_name
                    cjk_and_no_eng = track.cjk_name == self.cjk_name and not track.english_name
                    if eng_and_no_cjk or cjk_and_no_eng:
                        track.update_name(self.english_name, self.cjk_name, False)

    @property
    def name_tuple(self):
        return self.english_name, self.cjk_name

    def __repr__(self):
        if hasattr(self, '_obj'):
            return repr(self._obj)
        return super().__repr__()

    @cached_property
    def _is_plain_matchable(self):
        return not isinstance(self, WikiEntity) and hasattr(self, '_obj')

    def _aliases(self):
        if self._is_plain_matchable:
            # noinspection PyUnresolvedReferences
            aliases = (self._obj,) if isinstance(self._obj, str) else self._obj
            return set(aliases)

        _aliases = (
            getattr(self, attr, None) for attr in ('english_name', 'cjk_name', 'stylized_name', 'name', '_header_title')
        )
        aliases = list(filter(None, _aliases))
        try:
            # noinspection PyUnresolvedReferences
            aka = self.aka
        except AttributeError:
            pass
        else:
            if aka:
                if isinstance(aka, str):
                    aliases.append(aka)
                else:
                    aliases.extend(aka)

        # cjk_name = getattr(self, 'cjk_name', None)
        # if cjk_name:
        #     permutations = romanized_permutations(cjk_name)
        #     if len(permutations) > 1000:
        #         log.debug('There are {:,d} romanizations of {!r} - skipping them'.format(len(permutations), cjk_name))
        #     else:
        #         aliases.extend(permutations)

        aliases.extend([self.__abbrev_pat.sub('', alias) for alias in aliases])  # Remove periods from abbreviations
        return set(aliases)

    @property
    def _has_romanization(self):
        return bool(getattr(self, 'cjk_name', None))

    def _matches_romanization(self, text):
        return matches_permutation(text, self.cjk_name)

    def _additional_aliases(self):
        return set()

    @cached_property
    def aliases(self):
        for attr in ('lc_aliases', '_fuzzed_aliases', '_alias_langs', '_non_eng_langs'):
            try:
                del self.__dict__[attr]
            except KeyError:
                pass

        aliases = self._aliases()
        aliases.update(self._additional_aliases())
        return aliases

    @cached_property
    def lc_aliases(self):
        return [a.lower() for a in self.aliases]

    @cached_property
    def _fuzzed_aliases(self):
        if self._is_plain_matchable:
            # noinspection PyUnresolvedReferences
            fuzzed, cjk = self._fuzz_other(self._obj)
            # fuzzed, cjk, rom_permutations = self._fuzz_other(self._obj)
            self.cjk_name = cjk
            # self._rom_permutations = rom_permutations
            return fuzzed

        try:
            return set(filter(None, (fuzz_process(a, b) for a in self.aliases for b in (True, False))))
            # if isinstance(self, WikiSongCollection) or self._strip_special:
            #     return set(filter(None, (fuzz_process(a, strip_special=False) for a in self.aliases)))
            # return set(filter(None, (fuzz_process(a) for a in self.aliases)))
        except Exception as e:
            log.error('{}: Error fuzzing aliases: {}'.format(self, self.aliases))
            raise e

    @cached_property
    def _alias_langs(self):
        langs = set()
        for alias in self._fuzzed_aliases:
            langs.update(LangCat.categorize(alias, True))
        return langs

    @cached_property
    def _non_eng_langs(self):
        return {lang for lang in self._alias_langs if lang != LangCat.ENG}

    def matches(self, other, process=True):
        """
        Checks to see if one of the given strings is an exact match (after processing to remove spaces, punctuation,
        etc) for one of this entity's aliases (which undergo the same processing).  If passed a WikiEntity object, a
        basic equality test is performed instead.

        :param str|Iterable|WikiEntity other: The object to match against
        :param bool process: Run :func:`fuzz_process<.music.name_processing.fuzz_process>` on strings before comparing
          them (should only be set to False if the strings were already processed)
        :return bool: True if one of the given strings is an exact match for this entity, False otherwise
        """
        if isinstance(other, WikiEntity):
            # log.debug('Comparing {} [{}] to other={} [{}]'.format(self, self.url, other, other.url))
            return self.score_match(other)[0] >= 100
            # return self == other
        # log.debug('Comparing {} [{}] to other={}'.format(self, self.url, other))
        others = (other,) if isinstance(other, str) else filter(None, other)
        fuzzed_others = tuple(filter(None, (fuzz_process(o) for o in others) if process else others))
        if not fuzzed_others:
            log.warning('Unable to compare {} to {!r}: nothing to compare after processing'.format(self, other))
            return False
        return bool(self._fuzzed_aliases.intersection(fuzzed_others))

    def _fuzz_other(self, other, process=True):
        eng, cjk, permutations = None, None, None
        if isinstance(other, str):
            lang = LangCat.categorize(other)
            if lang == LangCat.MIX:
                try:
                    eng, cjk, extra = split_name(other, True)
                except ValueError:
                    others = (other,)
                    # if LangCat.contains_any(other, LangCat.asian_cats):
                    #     permutations = tuple(filter(None, (fuzz_process(o) for o in romanized_permutations(other) if o)))
                else:
                    if eng == 'live':
                        others = [cjk]
                    elif eng.lower().endswith(('ver', 'ver.', 'version')) and eng.count(' ') == 1:
                        others = [other, cjk]
                    else:
                        others = ['{} ({})'.format(eng, cjk), eng, cjk]

                    if extra:
                        others = ['{} ({})'.format(s, extra) for s in others] + others
            elif lang in LangCat.asian_cats:
                cjk = other
                others = (other,)
                # permutations = tuple(filter(None, (fuzz_process(o) for o in romanized_permutations(other) if o)))
            else:
                others = (other,)
        elif isinstance(other, WikiEntity):
            others = other._fuzzed_aliases
            process = False
        else:
            others = other

        # log.debug('_fuzz_other({!r}) pre-fuzz others={!r}'.format(other, others))
        if isinstance(self, WikiSongCollection) or not self._strip_special:
            fuzzed = tuple(filter(None, (fuzz_process(o, strip_special=False) for o in others) if process else others))
        else:
            fuzzed = tuple(filter(None, (fuzz_process(o) for o in others if o) if process else others))
        # return fuzzed, cjk, permutations
        return fuzzed, cjk

    @cached_property
    def __has(self):
        if isinstance(self, WikiTrack):
            self_name_lc = self.long_name.lower()
            return {'inst': 'inst' in self_name_lc, 'version': any(v in self_name_lc for v in ('ver.', 'version'))}
        elif self._is_plain_matchable:
            # noinspection PyUnresolvedReferences
            obj = self._obj
            if isinstance(obj, str):
                other_lc = obj.lower()
                return {'inst': 'inst' in other_lc, 'version': any(v in other_lc for v in ('ver.', 'version'))}
            else:
                return {
                    'inst': any('inst' in _other for _other in self._fuzzed_aliases),
                    'version': any(v in _other for v in ('ver.', 'version') for _other in self._fuzzed_aliases)
                }
        return {}

    @cached_property
    def __track_info(self):
        info = []
        # noinspection PyUnresolvedReferences
        obj = self._obj
        for _other in (obj,) if isinstance(obj, str) else obj:
            try:
                # noinspection PyUnresolvedReferences
                other_track_info = parse_track_info(self._track, _other, 'matching: {!r}'.format(_other))
            except Exception:
                pass
            else:
                info.append(other_track_info)
        return info

    @cached('_num_cache')
    def __nums(self, fuzzed_alias):
        return ''.join(self._int_pat.findall(fuzzed_alias))

    @cached('_match_cache')
    def score_match(self, other, process=True, track=None, disk=None, year=None, track_count=None, score_mod=0):
        """
        Score how closely this WikiEntity's aliases match the given strings.

        :param str|Iterable other: String or iterable that yields strings
        :param bool process: Run :func:`fuzz_process<.music.name_processing.fuzz_process>` on strings before comparing
          them (should only be set to False if the strings were already processed)
        :param int|None track: The track number if other represents a track
        :param int|none disk: The disk number if other represents a track
        :param int|None year: The release year if other represents an album
        :param int|None track_count: The number of tracks that the album being matched has
        :param int score_mod: The initial score modifier (if checks were made prior to calling this method)
        :return tuple: (score, best alias of this WikiEntity, best value from other)
        """
        if not isinstance(other, (str, WikiEntity)) and len(other) == 1:
            other = other[0]
        if isinstance(other, WikiEntity):
            if self._category != other._category and self._category is not None and other._category is not None:
                log.debug('Unable to compare {} to {!r}: incompatible categories'.format(self, other))
                return 0, None, None

        # TODO: avg of title.lower() & fuzzed title instead of only fuzzed?

        _log = logr['scoring']
        # if isinstance(self, WikiSongCollection):
        #     _log.setLevel(logging.NOTSET)
        # else:
        #     _log.setLevel(logging.WARNING)
        matchable = self.__cached(other, isinstance(self, WikiSongCollection), track)
        # log.debug('fuzz({!r}) => {!r}'.format(other, matchable._fuzzed_aliases))
        # _log.debug('fuzz({!r}) => {}'.format(other, len(matchable._fuzzed_aliases)))
        _log.debug('{!r}.score_match({!r})'.format(self, other))
        if not matchable._fuzzed_aliases:
            log.warning('Unable to compare {} to {!r}: nothing to compare after processing'.format(self, other))
            return 0, None, None
        elif isinstance(self, WikiTrack):
            if track is not None:
                if self.collection.contains_mixed_editions:
                    score_mod += 15 if str(self.num) == str(track) else -5
                else:
                    score_mod += 15 if str(self.num) == str(track) else -40
            if disk is not None:
                score_mod += 15 if str(self.disk) == str(disk) else -40

            self_has = self.__has
            other_has = matchable.__has
            for key, self_val in self_has.items():
                o_yes_self_no = other_has[key] and not self_val
                o_no_self_yes = self_val and not other_has[key]
                if o_yes_self_no or o_no_self_yes:
                    lang = self.language or self.collection.language or ''
                    ignore_due_to_lang = False
                    if key == 'version' and o_yes_self_no and lang:
                        lang = lang.lower()
                        ignore_due_to_lang = any(lang in a for a in matchable._fuzzed_aliases)
                    if ignore_due_to_lang:
                        _log.debug('{!r}=?={!r}: ignoring no {} due to language'.format(self, other, key))
                    else:
                        _log.debug('{!r}=?={!r}: score_mod-=25 (no {})'.format(self, other, key))
                        score_mod -= 25

            if self_has['version'] and other_has['version']:
                self_lang = (self.language or self.collection.language or '').lower()
                self_langs = ('chinese', 'mandarin') if self_lang in ('chinese', 'mandarin') else (self_lang,)
                scored_lang, scored_ver = False, False

                for other_track_info in matchable.__track_info:
                    # log.debug('{}: Comparing lang & version to: {!r} => {}'.format(self, other, other_track_info))
                    if not scored_lang:
                        other_lang = (other_track_info.get('language') or '').lower()
                        _log.debug('{}: Comparing to {!r} - lang {!r} =?= {!r}'.format(self, other, self_lang, other_lang))
                        if self_lang and other_lang:
                            score_mod += 15 if other_lang in self_langs else -15
                    if not scored_ver:
                        other_ver = (other_track_info.get('version') or '').lower()
                        self_ver = (self.version or '').lower()
                        _log.debug('{}: Comparing to {!r} - ver {!r} =?= {!r}'.format(self, other, self_ver, other_ver))
                        if self_ver and other_ver:
                            score_mod += 15 if other_ver == self_ver else -15
                    if scored_lang and scored_ver:
                        break
        elif isinstance(self, WikiSongCollection):
            if year is not None:
                try:
                    years_match = str(self.released.year) == str(year)
                except Exception:
                    pass
                else:
                    score_mod += 15 if years_match else -25
                    if years_match:
                        _log.debug('score_mod += 15: self.released.year=year={}'.format(year))
                    else:
                        _log.debug('score_mod -= 25: self.released.year={} != year={}'.format(self.released.year, year))
            if track_count is not None and self._part_track_counts:
                score_mod += 10 if track_count in self._part_track_counts else -20
                if track_count in self._part_track_counts:
                    _log.debug('score_mod += 10: track_count={} matches {}'.format(track_count, self._part_track_counts))
                else:
                    _log.debug('score_mod -= 20: track_count={} not in {}'.format(track_count, self._part_track_counts))

        best_score, best_alias, best_val = 0, None, None
        own_count = len(self._fuzzed_aliases)
        other_count = len(matchable._fuzzed_aliases)
        _log.debug('{}: Comparing {} aliases against {} aliases (=> {:,d} comparisons)'.format(self, own_count, other_count, own_count * other_count))

        # has_han_alias = any(LangCat.categorize(alias) == LangCat.HAN for alias in self._fuzzed_aliases)
        other_aliases = matchable._fuzzed_aliases
        for alias in self._fuzzed_aliases:
            alias_nums = self.__nums(alias)
            is_cjk_alias = LangCat.contains_any(alias, LangCat.asian_cats)
            # other_aliases = matchable._fuzzed_aliases
            # if not has_han_alias and matchable._rom_permutations:
            #     if LangCat.categorize(alias) in (LangCat.ENG, LangCat.MIX):
            #         other_aliases = chain(matchable._fuzzed_aliases, matchable._rom_permutations)

            for val in other_aliases:
                score = revised_weighted_ratio(alias, val)
                if score < 90:
                    if is_cjk_alias and LangCat.matches(val, LangCat.ENG):
                        score = 100 if self._matches_romanization(val) else score
                    elif not is_cjk_alias and LangCat.contains_any(val, LangCat.asian_cats):
                        score = 100 if matchable._matches_romanization(alias) else score

                if alias_nums != matchable.__nums(val):
                    score -= 30
                if ('live' in alias and 'live' not in val) or ('live' in val and 'live' not in alias):
                    score -= 25

                other_repr = other if isinstance(other, WikiEntity) else val
                _log.debug('{!r}=?={!r}: score={}, alias={!r}, val={!r}'.format(self, other_repr, score, alias, val))
                if score > best_score:
                    best_score, best_alias, best_val = score, alias, val
                if best_score >= 100:
                    break

        best_is_eng = LangCat.categorize(best_alias) == LangCat.ENG
        val_is_eng = LangCat.categorize(best_val) == LangCat.ENG
        if best_is_eng and not val_is_eng:
            score_mod -= 50
            _log.debug('score_mod -= 50: val_is_eng={}, best_is_eng={}'.format(val_is_eng, best_is_eng))

        if len(matchable._fuzzed_aliases) > 1 and self._non_eng_langs and best_is_eng:
            other_langs = matchable._non_eng_langs
            common_non_eng = self._non_eng_langs.intersection(other_langs)
            score_mod += 5 if common_non_eng else -15
            if common_non_eng:
                _log.debug('score_mod += 5: common non-eng langs: {}'.format(common_non_eng))
            else:
                _log.debug('score_mod -= 15: non-eng self:{} other:{}'.format(self._non_eng_langs, other_langs))

        if best_alias and best_val:
            if best_alias == best_val:
                score_mod += 10
                _log.debug('score_mod += 10: {!r} is an exact match for {!r}'.format(best_alias, best_val))

            if isinstance(self, WikiTrack):
                # noinspection PyUnresolvedReferences
                sm = self.__lang_ver_pat.search(best_alias)
                # noinspection PyUnresolvedReferences
                om = self.__lang_ver_pat.search(best_val)
                if sm and om and sm.group(2).lower().strip() == om.group(2).lower().strip():
                    simple_score, simple_alias, simple_val = WikiMatchable.score_simple(sm.group(1), om.group(1))
                    fmt = '{}[{}]=={}[{}] with score={}, but with language stripped, {}=={} with score={}'
                    _log.debug(fmt.format(self, best_alias, other, best_val, best_score, simple_alias, simple_val, simple_score), extra={'color': 'red'})
                    best_score = simple_score
            elif isinstance(self, WikiSongCollection):
                # noinspection PyUnresolvedReferences
                m_self = self.__part_pat.match(best_alias)
                # noinspection PyUnresolvedReferences
                m_other = self.__part_pat.match(best_val)
                if m_self and m_other:
                    score = revised_weighted_ratio(m_self.group(1), m_other.group(1))
                    best_score = int(best_score * score / 100)

        final_score = best_score + score_mod
        if final_score >= 100:
            if matchable.cjk_name and not getattr(self, 'cjk_name', None):
                log.debug('Updating {!r}.cjk_name => {!r}'.format(self, matchable.cjk_name))
                try:
                    self.update_name(None, matchable.cjk_name)
                except AttributeError:
                    pass
                # else:
                #     if isinstance(self, WikiTrack) and isinstance(self.collection, WikiFeatureOrSingle):
                #         if self.collection.english_name == self.english_name and not self.collection.cjk_name:
                #             self.collection.update_name(None, matchable.cjk_name)
            elif getattr(matchable, 'english_name', None) and not getattr(self, 'english_name', None):
                log.debug('Updating {!r}.english_name => {!r}'.format(self, matchable.english_name))
                try:
                    self.update_name(matchable.english_name, None)
                except AttributeError:
                    pass

        fmt = '{!r}=?={!r}: final_score={} (={} + {}), alias={!r}, val={!r}'
        _log.debug(fmt.format(self, other, final_score, best_score, score_mod, best_alias, best_val))
        return final_score, best_alias, best_val


class WikiEntity(WikiMatchable, metaclass=WikiEntityMeta):
    __instances = {}
    _category = None

    def __init__(self, uri_path=None, client=None, *, name=None, raw=None, no_fetch=False, **kwargs):
        if uri_path is None and name is None and raw is None:
            raise WikiEntityInitException('Unable to initialize a {} with no identifiers'.format(type(self).__name__))
        super().__init__()
        self.__additional_aliases = set()
        self._client = client
        self._uri_path = uri_path
        self._raw = raw if raw is not None else client.get_page(uri_path) if uri_path and not no_fetch else None
        self.english_name = None
        self.cjk_name = None
        if not name:
            self.name = uri_path
        elif isinstance(name, str):
            self.name = name
        else:
            if len(name) == 2:
                try:
                    self.update_name(*eng_cjk_sort(name))
                except ValueError as e:
                    self.name = name[0]
                    self._add_alias(name[1])
            else:
                self.name = name[0]
                self._add_aliases(name[1:])

        if isinstance(self._client, DramaWikiClient) and self._raw:
            self._header_title = soupify(self._raw, parse_only=bs4.SoupStrainer('h2', class_='title')).text
        else:
            self._header_title = None

    def _post_init(self):
        return

    def __repr__(self):
        return '<{}({!r}) @ {}>'.format(type(self).__name__, self.name, self._client._site if self._client else None)

    def __eq__(self, other):
        if not isinstance(other, WikiEntity):
            return False
        return self.name == other.name and self._raw == other._raw

    def __hash__(self):
        return hash((self.name, self._raw))

    def _add_alias(self, alias):
        self.__additional_aliases.add(alias)
        try:
            del self.__dict__['aliases']
        except KeyError:
            pass

    def _add_aliases(self, aliases):
        self.__additional_aliases.update(aliases)
        try:
            del self.__dict__['aliases']
        except KeyError:
            pass

    def _additional_aliases(self):
        return self.__additional_aliases

    @cached_property
    def url(self):
        if self._uri_path is None:
            return None
        return self._client.url_for(self._uri_path)

    @property
    def _soup(self):
        # soupify every time so that elements may be modified/removed without affecting other functions
        return soupify(self._raw, parse_only=bs4.SoupStrainer('div', id='mw-content-text')) if self._raw else None

    @cached_property
    def _side_info(self):
        """The parsed 'aside' / 'infobox' section of this page"""
        if not hasattr(self, '_WikiEntity__side_info'):
            _ = self._clean_soup

        try:
            return {} if not self.__side_info else self._client.parse_side_info(self.__side_info, self._uri_path)
        except Exception as e:
            log.error('Error processing side bar info for {}: {}'.format(self._uri_path, e))
            raise e

    @cached_property
    def _clean_soup(self):
        """The soupified page content, with the undesirable parts at the beginning removed"""
        try:
            content = self._soup.find('div', id='mw-content-text')
        except AttributeError as e:
            self.__side_info = None
            if self._soup is not None:
                log.warning(e)
            return None

        if isinstance(self._client, (KpopWikiClient, KindieWikiClient)):
            aside = content.find('aside')
            # if aside:
            #     log.debug('Extracting aside')
            self.__side_info = aside.extract() if aside else None

            for ele_id in ('wikipedia',):
                rm_ele = content.find(id=ele_id)
                if rm_ele:
                    # log.debug('Extracting: {}'.format(rm_ele))
                    rm_ele.extract()

            for ele_name in ('center',):
                rm_ele = content.find(ele_name)
                if rm_ele:
                    # log.debug('Extracting: {}'.format(rm_ele))
                    rm_ele.extract()

            for clz in ('dablink', 'hatnote', 'shortdescription', 'infobox'):
                rm_ele = content.find(class_=clz)
                if rm_ele:
                    # log.debug('Extracting: {}'.format(rm_ele))
                    rm_ele.extract()

            for rm_ele in content.find_all(class_='mw-empty-elt'):
                # log.debug('Extracting: {}'.format(rm_ele))
                rm_ele.extract()

            first_ele = content.next_element
            if getattr(first_ele, 'name', None) == 'dl':
                # log.debug('Extracting: {}'.format(first_ele))
                first_ele.extract()
        elif isinstance(self._client, DramaWikiClient):
            self.__side_info = None
            for clz in ('toc', 'thumbinner'):
                rm_ele = content.find(class_=clz)
                if rm_ele:
                    rm_ele.extract()

            for clz in ('toc', 'mw-editsection'):
                for rm_ele in content.find_all(class_=clz):
                    rm_ele.extract()
        elif isinstance(self._client, WikipediaClient):
            for rm_ele in content.select('[style~="display:none"]'):
                rm_ele.extract()

            infobox = content.find('table', class_=re.compile('infobox.*'))
            self.__side_info = infobox.extract() if infobox else None

            for rm_ele in content.find_all(class_='mw-empty-elt'):
                rm_ele.extract()

            bad_classes = (
                'toc', 'mw-editsection', 'reference', 'hatnote', 'infobox', 'noprint', 'box-Multiple_issues',
                'box-Unreliable_sources', 'box-BLP_sources', 'ambox-one_source'
            )
            for clz in bad_classes:
                for rm_ele in content.find_all(class_=clz):
                    rm_ele.extract()

            for clz in ('shortdescription', 'box-More_citations_needed'):
                rm_ele = content.find(class_=clz)
                if rm_ele:
                    rm_ele.extract()
        else:
            log.debug('No sanitization configured for soup objects from {}'.format(type(self._client).__name__))
        return content

    @cached_property
    def _all_anchors(self):
        return list(self._clean_soup.find_all('a'))

    def _has_no_valid_links(self, href, text):
        if not href and self._raw:
            # fmt = '{}: Seeing if text={!r} == anchor={!r} => a.text={!r}, a.class={!r}, a.href={!r}'
            for a in self._all_anchors:
                _href = a.get('href')
                # log.debug(fmt.format(self.url, text, a, a.text, a.get('class'), _href))
                if a.text == text:
                    if _href and '&redlink=1' not in _href:             # a valid link
                        return False
                    elif 'new' in a.get('class') and _href is None:     # displayed as a red link in a browser
                        return True
                elif _href:
                    _url = urlparse(_href[6:] if _href.startswith('/wiki/') else _href)
                    if _url.path == text:
                        return '&redlink=1' in _url.query
        elif href and '&redlink=1' in href:
            return True
        return False

    def _find_href(self, texts, categories=None):
        """
        :param container texts: A container holding one or more strings that should match the text property of an html
          anchor in this page
        :param None|container categories: A container holding one more more str categories to match against, or None to
          match against any non-None page category
        :return None|str: A url/uri_path from an anchor on this page if a match was found, otherwise None
        """
        if self._raw:
            return find_href(self._client, self._all_anchors, texts, categories)
        return None


class WikiPersonCollection(WikiEntity):
    _category = ('agency', 'competition', 'group', 'singer')


class WikiAgency(WikiPersonCollection):
    _category = 'agency'


class WikiCompetitionOrShow(WikiPersonCollection):
    _category = 'competition_or_show'


class WikiDiscography(WikiEntity):
    _category = 'discography'

    def __init__(self, uri_path=None, client=None, *, artist=None, **kwargs):
        super().__init__(uri_path, client, **kwargs)
        self.artist = artist
        self._albums, self._singles = parse_discography_page(self._uri_path, self._clean_soup, artist)


class WikiTVSeries(WikiEntity):
    _category = 'tv_series'

    def __init__(self, uri_path=None, client=None, **kwargs):
        super().__init__(uri_path, client, **kwargs)
        self.ost_hrefs = []
        if isinstance(self._client, WikipediaClient):
            page_text = self._clean_soup.text
            if LangCat.categorize(page_text) == LangCat.MIX:
                try:
                    name_parts = parse_name(page_text)
                except Exception as e:
                    fmt = '{} while processing intro for {}: {}'
                    log.warning(fmt.format(type(e).__name__, self._client.url_for(uri_path), e))
                    raise e
                else:
                    self.english_name, self.cjk_name, self.stylized_name, self.aka, self._info = name_parts
                    self.name = multi_lang_name(self.english_name, self.cjk_name)
            else:
                self.aka = []

            if self._side_info:
                self.aka.extend(self._side_info.get('also known as', []))
        elif self._side_info:
            self.name = self._side_info['name']
            self.aka = self._side_info.get('also known as', [])
        elif isinstance(self._client, DramaWikiClient):
            self.name = self._header_title
            if self._raw and not kwargs.get('no_init'):
                for section in ('Details', 'Detail', 'Season_1'):
                    info_header = self._clean_soup.find(id=section)
                    try:
                        ul = info_header.parent.find_next('ul')
                    except Exception as e:
                        if section == 'Season_1':
                            headlines = self._clean_soup.find_all(class_='mw-headline')
                            raise_error = True
                            if not any(span.get('id') in ('Details', 'Season_1') for span in headlines):
                                ul = self._clean_soup.find('ul')
                                try:
                                    raise_error = 'title' not in ul.find('li').text.lower()
                                except Exception:
                                    pass
                            if raise_error:
                                raise WikiEntityParseException('Unable to find info for {} from {}'.format(self, self.url)) from e
                        else:
                            continue

                    # noinspection PyUnboundLocalVariable
                    self._info = parse_drama_wiki_info_list(self._uri_path, ul, client)
                    if self._info is not None:
                        break
                    elif section == 'Season_1':
                        raise WikiEntityParseException('Info list could not be parsed for {} from {}'.format(self, self.url))

                title_parts = OrderedDict(
                    (k, v) for k, v in self._info.items() if any(ti in k for ti in ('title', 'name'))
                )
                first_title_key, first_title_part = next(iter(title_parts.items()))
                if 'chinese' in first_title_key:
                    han_parts = [
                        (k, v) for k, v in title_parts.items() if any(hi in k for hi in ('hangul', 'korean'))
                    ]
                    if len(han_parts) == 1:
                        first_title_key, first_title_part = han_parts[0]
                try:
                    self.english_name, self.cjk_name = first_title_part
                except ValueError as e:
                    err_msg = 'Unexpected show title for {}: {!r}'.format(self.url, first_title_part)
                    if isinstance(first_title_part, str) and LangCat.contains_any_not(first_title_part, LangCat.ENG):
                        eng_parts = [v for k, v in title_parts.items() if 'english' in k]
                        if not eng_parts:
                            eng_parts = [v for k, v in title_parts.items() if 'romaji' in k]
                        if len(eng_parts) == 1:
                            eng_part = eng_parts[0] if isinstance(eng_parts[0], str) else eng_parts[0][0]
                            if LangCat.categorize(eng_part) == LangCat.ENG:
                                self.english_name = eng_part
                                self.cjk_name = first_title_part
                            else:
                                log.error(err_msg)
                        elif len(eng_parts) > 1:
                            log.error('Found multiple eng title parts for {}: {}'.format(self.url, eng_parts))
                        else:
                            log.error(err_msg)
                    else:
                        log.error(err_msg)
                else:
                    eng, cjk = self.english_name, self.cjk_name
                    if not eng or (LangCat.contains_any(cjk, LangCat.asian_cats) and matches_permutation(eng, cjk)):
                        eng_parts = [v for k, v in title_parts.items() if 'english' in k]
                        if not eng_parts:
                            eng_parts = [v for k, v in title_parts.items() if 'romaji' in k]

                        if len(eng_parts) == 1:
                            eng_part = eng_parts[0] if isinstance(eng_parts[0], str) else eng_parts[0][0]
                            if LangCat.categorize(eng_part) == LangCat.ENG:
                                if self.english_name:
                                    self._add_alias(self.english_name)
                                self.english_name = eng_part
                            else:
                                log.debug('Unexpected eng title lang for {}: {!r}'.format(self.url, eng_part))
                        elif len(eng_parts) > 1:
                            log.debug('Found multiple eng title parts for {}: {}'.format(self.url, eng_parts))

                # if not self.english_name and not self.cjk_name:
                #     raise WikiEntityParseException('Title was not found for {} from {}'.format(self, self.url))

                if self._header_title and LangCat.categorize(self._header_title) == LangCat.ENG:
                    if self.english_name and self.cjk_name and self.english_name != self._header_title:
                        eng, cjk = self.english_name, self.cjk_name
                        if LangCat.contains_any(cjk, LangCat.asian_cats) and matches_permutation(eng, cjk):
                            self._add_alias(self.english_name)
                            self.english_name = self._header_title
                    elif self.cjk_name and not self.english_name:
                        self.english_name = self._header_title

                if self.english_name and self.cjk_name:
                    self.name = multi_lang_name(self.english_name, self.cjk_name)
                self.aka = self._info.get('also known as', [])
                ost = self._info.get('original soundtrack') or self._info.get('original soundtracks')
                if ost:
                    self.ost_hrefs.append(list(ost.values())[0])

                ost_tag_func = lambda tag: tag.name == 'li' and tag.text.lower().startswith('original soundtrack')
                try:
                    for li in self._clean_soup.find_all(ost_tag_func):
                        href = li.find('a').get('href')
                        if href and href not in self.ost_hrefs:
                            self.ost_hrefs.append(href)
                except Exception as e:
                    msg = 'Error processing OST links for {} from {}'.format(self, self.url)
                    raise WikiEntityParseException(msg) from e
        else:
            self.aka = []

    def _additional_aliases(self):
        addl_aliases = set()
        love_rx = re.compile('love', re.IGNORECASE)
        luv_rx = re.compile('luv', re.IGNORECASE)
        for alias in self._aliases():
            lc_alias = alias.lower()
            if 'love' in lc_alias:
                addl_aliases.add(love_rx.sub('Luv', alias))
            elif 'luv' in lc_alias:
                addl_aliases.add(luv_rx.sub('Love', alias))
        return addl_aliases


class WikiArtist(WikiPersonCollection):
    _category = ('group', 'singer')
    _known_artists = set()
    __known_artists_loaded = False

    def __init__(self, uri_path=None, client=None, *, name=None, strict=True, **kwargs):
        super().__init__(uri_path, client, name=name, **kwargs)
        self._tv_appearances = None
        self.english_name, self.cjk_name, self.stylized_name, self.aka = None, None, None, None
        if self._raw and not kwargs.get('no_init'):
            if isinstance(self._client, DramaWikiClient):
                ul = self._clean_soup.find(id='Profile').parent.find_next('ul')
                self._profile = parse_drama_wiki_info_list(self._uri_path, ul, client)
                if self._profile is None:
                    raise WikiEntityParseException('Error parsing profile for {} from {}'.format(self, self.url))
                try:
                    self._tv_appearances = parse_tv_appearances(self._uri_path, self._clean_soup, self)
                except WikiEntityParseException as e:
                    log.log(7, 'No TV shows section found for {}: {}'.format(self, e))

                name_parts = OrderedDict((k, v) for k, v in self._profile.items() if 'name' in k)
                first_name_key, first_name_part = next(iter(name_parts.items()))
                try:
                    self.english_name, self.cjk_name = first_name_part
                except ValueError as e:
                    err_msg = 'Unexpected name for {}: {!r}'.format(self.url, first_name_part)
                    if isinstance(first_name_part, str) and LangCat.contains_any_not(first_name_part, LangCat.ENG):
                        eng_parts = [v for k, v in name_parts.items() if 'english' in k]
                        if not eng_parts:
                            eng_parts = [v for k, v in name_parts.items() if 'romaji' in k]
                        if len(eng_parts) == 1:
                            eng_part = eng_parts[0] if isinstance(eng_parts[0], str) else eng_parts[0][0]
                            if LangCat.categorize(eng_part) == LangCat.ENG:
                                self.english_name = eng_part
                                self.cjk_name = first_name_part
                            else:
                                raise WikiEntityInitException(err_msg)
                        else:
                            raise WikiEntityInitException(err_msg)
                    else:
                        raise WikiEntityInitException(err_msg)

                # try:
                #     self.english_name, self.cjk_name = self._profile.get('name', self._profile.get('group name'))
                # except ValueError as e:
                #     _name = self._profile.get('name', self._profile.get('group name'))
                #     raise WikiEntityInitException('Error splitting tuple for name={!r} for {} from {}'.format(_name, self, self.url))

                # If eng name has proper eng name + romanized hangul name, remove the romanized part
                if self.english_name and self.cjk_name and '(' in self.english_name and self.english_name.endswith(')'):
                    m = re.match(r'^(.*)\((.*)\)$', self.english_name)
                    if m:
                        lc_nospace_rom = ''.join(m.group(1).lower().split())
                        if matches_permutation(lc_nospace_rom, self.cjk_name):
                            self.english_name = m.group(2).strip()
                        # for permutation in romanized_permutations(self.cjk_name):
                        #     if ''.join(permutation.split()) == lc_nospace_rom:
                        #         self.english_name = m.group(2).strip()
                        #         break
                elif self.cjk_name and not self.english_name and 'name (romaji)' in self._profile:
                    self.english_name = self._profile['name (romaji)']
            elif isinstance(self._client, WikipediaClient):
                page_text = self._clean_soup.text
                if LangCat.categorize(page_text) == LangCat.MIX:
                    rev_links = {href: text for text, href in link_tuples(self._all_anchors)}
                    try:
                        name_parts = parse_name(page_text, rev_links)
                    except Exception as e:
                        fmt = '{} while processing intro(1) for {}: {}'
                        log.warning(fmt.format(type(e).__name__, self._client.url_for(uri_path), e))
                        if strict:
                            raise e
                    else:
                        self.english_name, self.cjk_name, self.stylized_name, self.aka, self._info = name_parts
                else:
                    self.english_name = self._side_info.get('name')
            else:
                try:
                    name_parts = parse_name(self._clean_soup.text)
                except Exception as e:
                    fmt = '{} while processing intro(2) for {}: {}'
                    log.warning(fmt.format(type(e).__name__, self._client.url_for(uri_path), e))
                    if strict:
                        raise e
                else:
                    self.english_name, self.cjk_name, self.stylized_name, self.aka, self._info = name_parts

        if name and not any(val for val in (self.english_name, self.cjk_name, self.stylized_name)):
            self.english_name, self.cjk_name = split_name(name)

        self.name = multi_lang_name(self.english_name, self.cjk_name)
        if self.english_name and isinstance(self._client, KpopWikiClient):
            type(self)._known_artists.add(self.english_name.lower())

        self._albums, self._singles = None, None

    def __repr__(self):
        try:
            name = self.stylized_name or self.qualname
        except AttributeError:
            name = self._uri_path
        return '<{}({!r})@{}>'.format(type(self).__name__, name, self._client._site if self._client else None)

    def __lt__(self, other):
        comparison_type_check(self, other, (WikiArtist, str), '<')
        return (self.name < other.name) if isinstance(other, WikiArtist) else (self.name < other)

    def __gt__(self, other):
        comparison_type_check(self, other, (WikiArtist, str), '>')
        return (self.name > other.name) if isinstance(other, WikiArtist) else (self.name > other)

    @classmethod
    def known_artist_eng_names(cls):
        if not cls.__known_artists_loaded:
            cls.__known_artists_loaded = True
            known_artists_path = Path(__file__).resolve().parents[3].joinpath('music/artist_dir_to_artist.json')
            with open(known_artists_path.as_posix(), 'r', encoding='utf-8') as f:
                artists = json.load(f)
            cls._known_artists.update((split_name(artist)[0].lower() for artist in artists.values()))
        return cls._known_artists

    @classmethod
    def known_artists(cls):
        for name in sorted(cls.known_artist_eng_names()):
            yield WikiArtist(name=name)

    @cached(True, lock=True)
    def for_alt_site(self, site_or_client):
        client = WikiClient.for_site(site_or_client) if isinstance(site_or_client, str) else site_or_client
        if self._client._site == client._site:
            return self
        try:
            candidate = type(self)(aliases=(self.english_name, self.cjk_name), client=client)
        except CodeBasedRestException as e:
            pass
        except AmbiguousEntityException as e:
            if e.alternatives:
                of_group = getattr(self.member_of, 'english_name', None) if hasattr(self, 'member_of') else None
                return e.find_matching_alternative(type(self), self.aliases, associated_with=of_group, client=client)
        else:
            if candidate._uri_path and candidate._raw:
                candidate._add_aliases(self.aliases)
                self._add_aliases(candidate.aliases)
                if self.english_name and self.cjk_name and (not candidate.english_name or not candidate.cjk_name):
                    candidate.update_name(self.english_name, self.cjk_name)
                elif candidate.english_name and candidate.cjk_name and (not self.english_name or not self.cjk_name):
                    self.update_name(candidate.english_name, candidate.cjk_name)
                return candidate

        # log.debug('{}: Could not find {} version by name'.format(self, client))
        for i, (text, uri_path) in enumerate(client.search('|'.join(sorted(self.aliases)))):
            candidate = type(self)(uri_path, client=client)
            # log.debug('{}: Validating candidate={}'.format(self, candidate))
            if candidate.matches(self):
                candidate._add_aliases(self.aliases)
                self._add_aliases(candidate.aliases)
                if self.english_name and self.cjk_name and (not candidate.english_name or not candidate.cjk_name):
                    candidate.update_name(self.english_name, self.cjk_name)
                elif candidate.english_name and candidate.cjk_name and (not self.english_name or not self.cjk_name):
                    self.update_name(candidate.english_name, candidate.cjk_name)
                return candidate
            elif i > 4:
                break

        raise WikiEntityInitException('Unable to find valid {} version of {}'.format(client, self))

    @cached_property
    def _alt_entities(self):
        pages = []
        for client_cls in (KpopWikiClient, WikipediaClient):
            if not isinstance(self._client, client_cls):
                try:
                    page = WikiArtist(None, client_cls(), name=self._uri_path)
                except Exception as e:
                    log.debug('Unable to retrieve alternate {} entity for {}: {}'.format(client_cls.__name__, self, e))
                else:
                    pages.append(page)
        return pages

    @cached_property
    def _disco_page(self):
        if self._albums or self._singles:
            return self
        elif not isinstance(self._client, WikipediaClient):
            site = WikipediaClient._site
            try:
                alt_artist = self.for_alt_site(site)
            except Exception as e:
                log.debug('{}: Error finding {} version: {}'.format(self, site, e))
            else:
                return alt_artist._disco_page
        elif isinstance(self._client, WikipediaClient):
            disco_links = {}
            for a in self._soup.find_all('a'):
                a_text = a.text.lower() if a.text else ''
                if 'discography' in a_text:
                    href = a.get('href') or ''
                    href = href[6:] if href.startswith('/wiki/') else href
                    remaining = ''.join(a_text.partition('discography')[::2]).strip()
                    if href and '#' not in href and (not remaining or self.matches(remaining)):
                        if 'sm station' not in a.get('title', '').lower():
                            disco_links[a] = href
            if disco_links:
                uri_path = None
                if len(disco_links) == 1:
                    a, uri_path = disco_links.popitem()
                else:
                    for a, _uri_path in disco_links.items():
                        log.debug('Examining a={}, parent: {!r}'.format(a, a.parent))
                        a_text = a.parent.text.lower()
                        if any(val in a_text for val in ('main article', self.english_name.lower(), self.cjk_name)):
                            uri_path = _uri_path
                            break
                    else:
                        fmt = '{}: Too many different discography links found: {}'
                        log.error(fmt.format(self, ', '.join(sorted(map(str, disco_links)))), extra={'color': 'yellow'})

                if uri_path:
                    client = WikipediaClient()
                    try:
                        try:
                            return WikiDiscography(uri_path, client, artist=self)
                        except WikiTypeError as e:
                            return WikiArtist(uri_path, client)
                    except Exception as e:
                        fmt = '{}: Error retrieving discography page {}: {}'
                        log.error(fmt.format(self, client.url_for(uri_path), e))

        return None

    @property
    def _discography(self):
        if self._albums:            # Will only be set for non-kwiki sources
            return self._albums
        elif isinstance(self._client, KpopWikiClient):
            return parse_discography_section(self, self._clean_soup)
        elif isinstance(self._client, WikipediaClient):   # Pretend to be a WikiDiscography when both are on same page
            try:
                self._albums, self._singles = parse_discography_page(self._uri_path, self._clean_soup, self)
            except Exception as e:
                log.debug('{}: Error parsing discography info from {}: {}'.format(self, self.url, e))
                log.log(19, traceback.format_exc())

            if not self._albums and not self._singles:
                disco_page = self._disco_page
                if disco_page:
                    self._albums, self._singles = disco_page._albums, disco_page._singles
        elif isinstance(self._client, DramaWikiClient):
            try:
                self._albums = parse_artist_osts(self._uri_path, self._clean_soup, self)
            except WikiEntityParseException as e:
                log.debug('{}: Error parsing discography from {}: {}'.format(self, self.url, e))
                self._albums = None

        if self._albums:
            return self._albums

        client_host = getattr(self._client, 'host', None)
        if self._singles:
            log.debug('{}: Found singles in discography on {}, but no albums'.format(self, client_host))
        else:
            log.debug('{}: No discography content could be found from {}'.format(self, client_host))
        return []

    @cached_property
    def discography(self):
        discography = []
        for entry in self._discography:
            if entry['is_ost'] and not (entry.get('wiki') == 'wiki.d-addicts.com' and entry.get('uri_path')):
                client = WikiClient.for_site('wiki.d-addicts.com')
                title = entry['title']
                m = re.match('^(.*)\s+(?:Part|Code No)\.?\s*\d+$', title, re.IGNORECASE)
                if m:
                    title = m.group(1).strip()
                uri_path = client.normalize_name(title)
                if not entry.get('uri_path'):
                    entry['uri_path'] = uri_path
                # log.debug('Normalized title={!r} => uri_path={!r}'.format(title, uri_path))
            else:
                client = WikiClient.for_site(entry['wiki'])
                uri_path = entry['uri_path']
                title = entry['title']

            cls = WikiSongCollection
            if not uri_path:
                base_type = entry.get('base_type')
                if base_type == 'osts':
                    cls = WikiSoundtrack
                elif any(val in base_type for val in ('singles', 'collaborations', 'features')):
                    cls = WikiFeatureOrSingle
                elif any(val in base_type for val in ('albums', 'eps', 'extended plays', 'single album')):
                    cls = WikiAlbum
                else:
                    log.debug('{}: Unexpected base_type={!r} for {}'.format(self, base_type, entry), extra={'color': 9})

            try:
                try:
                    discography.append(cls(uri_path, client, disco_entry=entry, artist_context=self))
                except WikiTypeError as e:
                    if isinstance(client, DramaWikiClient):
                        if e.category == 'tv_series':
                            series = WikiTVSeries(uri_path, client)
                            found = False
                            if series.ost_hrefs:
                                for ost_href in series.ost_hrefs:
                                    ost = WikiSongCollection(ost_href, client, disco_entry=entry, artist_context=self)
                                    if len(series.ost_hrefs) == 1 or ost.matches(title):
                                        discography.append(ost)
                                        found = True
                                        break
                            if not found:
                                fmt = '{}: Error processing discography entry in {} for {!r} / {!r}: {}'
                                msg = fmt.format(self, self.url, entry['uri_path'], entry['title'], e)
                                log.error(msg, extra={'color': 13})
                    else:
                        fmt = '{}: Error processing discography entry in {} for {!r} / {!r}: {}'
                        log.error(fmt.format(self, self.url, entry['uri_path'], entry['title'], e), extra={'color': 13})
                except CodeBasedRestException as http_e:
                    if entry['is_ost'] and not isinstance(self._client, DramaWikiClient):
                        ost = find_ost(self, title, entry)
                        if ost:
                            discography.append(ost)
                        else:
                            log.log(9, '{}: Unable to find wiki page or alternate matches for {}'.format(self, entry))
                            ost = cls(uri_path, client, disco_entry=entry, artist_context=self, no_fetch=True)
                            discography.append(ost)
                            # raise http_e
                    else:
                        url = client.get_url_for(uri_path, allow_alt_sites=True)
                        if urlparse(url).hostname != self._client.host:
                            log.debug('{}: {} has a bad link for {} to {}'.format(self, self.url, entry['title'], url))
                        else:
                            fmt = '{}: Unable to find wiki page for {} via {}\n{}'
                            log.debug(fmt.format(self, entry, url, traceback.format_exc()))
                        alb = cls(uri_path, client, disco_entry=entry, artist_context=self, no_fetch=True)
                        discography.append(alb)
                        # raise http_e
            except MusicWikiException as e:
                fmt = '{}: Error processing discography entry in {} for {!r} / {!r}: {}\n{}'
                msg = fmt.format(self, self.url, entry['uri_path'], entry['title'], e, traceback.format_exc())
                log.error(msg, extra={'color': 13})
                # raise e

        if self._singles:
            for group in self._singles:
                group_type = group['type']
                group_sub_type = group['sub_type']
                if any(gtype in ('other charted songs', ) for gtype in (group_type, group_sub_type)):
                    continue
                elif any('soundtrack' in (group.get(k) or '') for k in ('sub_type', 'type')):
                    soundtracks = defaultdict(list)
                    for track in group['tracks']:
                        soundtracks[track['album']].append(track)

                    for ost_name, tracks in soundtracks.items():
                        disco_entry = {'title': ost_name, 'is_ost': True, 'track_info': tracks, 'base_type': 'osts'}
                        album_info = {
                            'track_lists': [{'section': None, 'tracks': tracks}], 'num': None, 'type': 'OST',
                            'repackage': False, 'length': None, 'released': None, 'links': []
                        }
                        alb = WikiSoundtrack(
                            None, self._client, no_type_check=True, disco_entry=disco_entry, album_info=album_info,
                            artist_context=self
                        )
                        discography.append(alb)
                else:
                    for track in group['tracks']:
                        name = track['name_parts']

                        collabs = track.get('collaborators', [])
                        try:
                            collabs = set(collabs)
                        except TypeError:                   # dict is not hashable
                            collab_dicts = list(collabs)
                        else:
                            # collabs.update(l[0] for l in track.get('links', []))
                            collab_dicts = [
                                collab if isinstance(collab, dict) else {'artist': eng_cjk_sort(collab)}
                                for collab in collabs
                            ]

                        track['collaborators'] = collab_dicts
                        try:
                            disco_entry = {
                                'title': name, 'collaborators': collab_dicts,
                                'base_type': SINGLE_TYPE_TO_BASE_TYPE[group_sub_type]
                            }
                        except KeyError as e:
                            err_msg = '{}: Unexpected single sub_type={!r} on {}'.format(self, group_sub_type, self.url)
                            raise WikiEntityParseException(err_msg) from e

                        # fmt = '{}: Adding single type={!r} subtype={!r} name={!r} collabs={}'
                        # log.debug(fmt.format(self, group_type, group_sub_type, name, collabs))

                        # disco_entry = {'title': name}
                        album_info = {'track_lists': [{'section': None, 'tracks': [track]}]}
                        single = WikiFeatureOrSingle(
                            None, self._client, disco_entry=disco_entry, album_info=album_info, artist_context=self,
                            no_fetch=True, name=name
                        )
                        discography.append(single)

        by_title = defaultdict(list)
        for entry in discography:
            by_title[entry.title()].append(entry)

        for title, entries in by_title.items():
            if len(entries) > 1:
                by_lang = defaultdict(list)
                for entry in entries:
                    by_lang[entry.language or 'Korean'].append(entry)

                for lang, _entries in by_lang.items():
                    # log.debug('{}: title={!r} has {} {} entries'.format(self, title, len(_entries), lang))
                    suffix = ' ({} Ver.)'.format(lang) if lang != 'Korean' else ''
                    if len(_entries) > 1:
                        for entry in _entries:
                            entry.update_name(
                                '{}{} [{}]'.format(entry.english_name, suffix, entry.num_and_type), None, False
                            )
                    else:
                        for entry in _entries:
                            entry.update_name('{}{}'.format(entry.english_name, suffix), None, False)

        return discography

    @cached_property
    def soundtracks(self):
        return [album for album in self.discography if isinstance(album, WikiSoundtrack)]

    @cached_property
    def singles(self):
        return [album for album in self.discography if isinstance(album, WikiFeatureOrSingle)]

    @cached()
    def expected_rel_path(self):
        artist = self
        if self._client and not isinstance(self._client, KpopWikiClient):
            try:
                artist = self.for_alt_site(KpopWikiClient._site)
            except Exception as e:
                pass
        return Path(sanitize_path(artist.english_name))

    @cached_property
    def associated_acts(self):
        associated = []
        _associated = self._side_info.get('associated', {})
        if not _associated:
            _associated = self._side_info.get('associated acts', {})
        for text, href in _associated.items():
            # log.debug('{}: Associated act from {}: a.text={!r}, a.href={!r}'.format(self, self.url, text, href))
            try:
                associated.append(WikiPersonCollection(href, name=text, client=self._client))
            except WikiTypeError as e:
                log.debug('{}: Unexpected type for associated act with name={!r} href={!r}'.format(self, text, href))

        if isinstance(self._client, DramaWikiClient):
            trivia_span = self._clean_soup.find('span', id='Trivia')
            if trivia_span:
                trivia_container = None
                for i, sibling in enumerate(trivia_span.parent.next_siblings):
                    if sibling.name == 'ul':
                        trivia_container = sibling
                        break
                    elif i > 2:
                        break

                if trivia_container:
                    pat = re.compile('KPOP group: .+ of (.*)', re.IGNORECASE)
                    for li in trivia_container.find_all('li'):
                        li_text = li.text.strip()
                        m = pat.match(li_text)
                        if m:
                            for artist in split_artist_list(m.group(1), self, tuple(li.find_all('a')), self._client)[0]:
                                group = artist['artist']
                                href = artist['artist_href']
                                a_act = WikiPersonCollection(href, name=group, client=self._client, no_fetch=not href)
                                log.debug('{}: Found associated act: {}'.format(self, a_act))
                                associated.append(a_act)

        return associated

    def find_song_collection(self, name, min_score=75, include_score=False, allow_alt=True, **kwargs):
        if isinstance(name, str):
            if name.lower().startswith('full album'):
                name = (name, name[10:].strip())
        match_fmt = '{}: {} matched {!r} with score={} because its alias={!r} =~= {!r}'
        best_score, best_alias, best_val, best_coll = 0, None, None, None
        for collection in self.discography:
            score, alias, val = collection.score_match(name, **kwargs)
            if score > best_score:
                best_score, best_alias, best_val, best_coll = score, alias, val, collection
                log.log(3, match_fmt.format(self, best_coll, name, best_score, best_alias, best_val))
                if score >= 100:
                    break

        if best_score > min_score:
            if allow_alt and isinstance(self._client, KpopWikiClient) and not best_coll.get_tracks():
                site = WikipediaClient._site
                try:
                    alt_artist = self.for_alt_site(site)
                except Exception as e:
                    log.debug('{}: Error finding {} version: {}'.format(self, site, e))
                    # traceback.print_exc()
                else:
                    alt_coll, alt_score = alt_artist.find_song_collection(name, min_score, True, **kwargs)
                    if alt_coll and alt_score >= best_score and alt_coll.get_tracks():
                        best_coll, best_score = alt_coll, alt_score

            if best_score < 95:
                log.debug(match_fmt.format(self, best_coll, name, best_score, best_alias, best_val))
            return (best_coll, best_score) if include_score else best_coll

        aliases = (name,) if isinstance(name, str) else name
        if isinstance(self._client, (KpopWikiClient, WikipediaClient)) and any('OST' in a.upper() for a in aliases):
            collection, score = self._find_ost(name, aliases, min_score, best_score, match_fmt, **kwargs)
            if (score > best_score) and (score > min_score):
                return (collection, score) if include_score else collection

        if allow_alt and isinstance(self._client, KpopWikiClient):
            site = WikipediaClient._site
            try:
                alt_artist = self.for_alt_site(site)
            except Exception as e:
                log.debug('{}: Error finding {} version: {}'.format(self, site, e))
            else:
                return alt_artist.find_song_collection(name, min_score=min_score, include_score=include_score, **kwargs)

        return (None, -1) if include_score else None

    def _find_ost(self, name, aliases, min_score, best_score, match_fmt, **kwargs):
        site = DramaWikiClient._site
        try:
            alt_artist = self.for_alt_site(site)
        except Exception as e:
            if any('OST' in alias.upper() for alias in aliases):
                ost_name = name if isinstance(name, str) else next(iter(name))
                match_aliases = [name] if isinstance(name, str) else list(name)
                # try:
                #     no_part_name = WikiSoundtrack._ost_name_rx.match(ost_name).group(1).strip()
                # except Exception:
                #     pass
                # else:
                #     log.info('no_part_name({!r}) = {!r}'.format(name, no_part_name))
                #     match_aliases.insert(0, no_part_name)

                log.debug('{}: Using find_ost({!r})'.format(self, ost_name))

                ost = find_ost(self, ost_name, {'title': ost_name})
                if ost:
                    log.debug('{}: Found OST via find_ost: {} @ {}'.format(self, ost, ost.url))

                    score, alias, val = ost.score_match(tuple(match_aliases), **kwargs)

                    log.debug(match_fmt.format(self, ost, name, score, alias, val))

                    if score > best_score:
                        best_score, best_alias, best_val, best_coll = score, alias, val, ost
                        log.debug(match_fmt.format(self, best_coll, name, best_score, best_alias, best_val))
                        if best_score > min_score:
                            if best_score < 95:
                                log.debug(match_fmt.format(self, best_coll, name, best_score, best_alias, best_val))
                            return best_coll, best_score

            log.debug('{}: Error finding {} version: {}'.format(self, site, e))
            return None, -1
        else:
            return alt_artist.find_song_collection(name, min_score=min_score, include_score=True, **kwargs)

    def find_track(
        self, track_name, album_name=None, min_score=75, include_score=False, track=None, disk=None, year=None, **kwargs
    ):
        year = str(year) if year else year
        # alb_name_langs = LangCat.categorize(album_name, True) if album_name else set()

        best_score, best_track, best_coll = 0, None, None
        for collection in self.discography:
            track, score = collection.find_track(
                track_name, min_score=min_score, include_score=True, track=track, disk=disk, **kwargs
            )
            if score > 0:
                collection = track.collection
                if year and collection.year:
                    score += 15 if str(collection.year) == year else -15
                if album_name:
                    if collection.matches(album_name):
                        score += 15

                if score > best_score:
                    best_score, best_track, best_coll = score, track, collection

        if best_score > min_score:
            if best_score < 95:
                if album_name:
                    match_fmt = '{}: {} from {} matched {!r} from {!r} with score={}'
                    log.debug(match_fmt.format(self, best_track, best_coll, track_name, album_name, best_score))
                else:
                    match_fmt = '{}: {} from {} matched {!r} with score={}'
                    log.debug(match_fmt.format(self, best_track, best_coll, track_name, best_score))
            return (best_track, best_score) if include_score else best_track
        elif isinstance(self._client, KpopWikiClient):
            site = WikipediaClient._site
            try:
                alt_artist = self.for_alt_site(site)
            except Exception as e:
                log.debug('{}: Error finding {} version: {}'.format(self, site, e))
            else:
                return alt_artist.find_track(
                    track_name, album_name, min_score=min_score, include_score=include_score, track=track, disk=disk,
                    year=year, **kwargs
                )

        return (None, -1) if include_score else None

    @cached_property
    def qualname(self):
        """Like an FQDN for artists - if this is a WikiSinger, include the group they are a member of"""
        return self.name

    def _as_collab(self):
        return {'artist': (self.english_name, self.cjk_name), 'artist_href': self._uri_path}

    def find_associated(self, name, min_score=75, include_score=False):
        match_fmt = '{}: {} matched {} {!r} with score={} because its alias={!r} =~= {!r}'
        best_score, best_alias, best_val, best_type, best_entity = 0, None, None, None, None
        for etype in ('member', 'sub_unit', 'associated_act'):
            # log.debug('Processing {}\'s {}s'.format(self, etype))
            try:
                egroup = getattr(self, etype + 's')
            except AttributeError as e:
                # log.debug('{}: Error getting attr \'{}s\': {}\n{}'.format(self, etype, e, traceback.format_exc()))
                continue
            for entity in egroup:
                score, alias, val = entity.score_match(name)
                if score >= 100:
                    # log.debug(match_fmt.format(self, entity, etype, name, score, alias, val), extra={'color': 100})
                    return (score, entity) if include_score else entity
                elif score > best_score:
                    best_score, best_alias, best_val, best_type, best_entity = score, alias, val, etype, entity

            if best_score > min_score:
                msg = match_fmt.format(self, best_entity, best_type, name, best_score, best_alias, best_val)
                log.debug(msg, extra={'color': 100})
                return (best_score, best_entity) if include_score else best_entity

        fmt = 'Unable to find member/sub-unit/associated act of {} named {!r}'
        raise MemberDiscoveryException(fmt.format(self, name))

    @cached_property
    def tv_shows(self):
        if self._tv_appearances is None:
            return []
        shows = []
        for show in self._tv_appearances:
            if show['href'] and '&redlink=1' not in show['href']:
                try:
                    shows.append(WikiTVSeries(show['href'], self._client))
                except WikiTypeError as e:
                    log.debug('{}\'s show {} is not a TV Series: {}'.format(self, show, e))
        return shows


class WikiGroup(WikiArtist):
    _category = 'group'

    def __init__(self, uri_path=None, client=None, **kwargs):
        super().__init__(uri_path, client, **kwargs)
        self.subunit_of = None
        if self._raw and not kwargs.get('no_init'):
            clean_soup = self._clean_soup
            if re.search('^.* is (?:a|the) .*?sub-?unit of .*?group', clean_soup.text.strip()):
                for i, a in enumerate(clean_soup.find_all('a')):
                    href = a.get('href') or ''
                    href = href[6:] if href.startswith('/wiki/') else href
                    if href and (href != self._uri_path):
                        try:
                            self.subunit_of = WikiGroup(href, client=self._client)
                        except WikiTypeError:
                            if i > 3:
                                log.warning('Unable to find parent group for {}'.format(self))
                                break
                        else:
                            break

    def __contains__(self, item):
        return item in self.members

    def _members(self):
        if not self._raw:
            return
        elif isinstance(self._client, KpopWikiClient):
            yield from find_group_members(self, self._clean_soup)
        elif isinstance(self._client, WikipediaClient):
            yield from parse_wikipedia_group_members(self, self._clean_soup)
        elif isinstance(self._client, DramaWikiClient):
            yield from parse_dwiki_group_members(self, self._clean_soup)
        else:
            log.warning('{}: No group member parsing has been configured for {}'.format(self, self.url))

    @cached_property
    def members(self):
        members = []
        for href, member_name in self._members():
            log.debug('{}: Looking up member href={!r} name={!r}'.format(self, href, member_name))
            if member_name:
                name = member_name if isinstance(member_name, str) else member_name[0]
            else:
                name = None
            if name and self._has_no_valid_links(href, name):
                fmt = '{}: Skipping page search for member={!r} found on {} because it has a red link'
                log.log(5, fmt.format(self, member_name, self.url), extra={'color': 94})
                members.append(WikiSinger(None, name=member_name, no_fetch=True, _member_of=self))
            elif href:
                try:
                    members.append(WikiSinger(href, _member_of=self))
                except CodeBasedRestException as e:
                    if not isinstance(self._client, KpopWikiClient):
                        members.append(WikiSinger(href, _member_of=self, client=self._client))
                    else:
                        raise e
            else:
                members.append(WikiSinger(None, name=member_name, no_fetch=True, _member_of=self))
        return members

    @cached_property
    def sub_units(self):
        su_ele = self._clean_soup.find(id=re.compile('sub[-_]?units', re.IGNORECASE))
        if not su_ele:
            return []

        while su_ele and not su_ele.name.startswith('h'):
            su_ele = su_ele.parent
        ul = su_ele.next_sibling.next_sibling
        if not ul or ul.name != 'ul':
            raise RuntimeError('Unexpected sibling element for sub-units')

        sub_units = []
        for li in ul.find_all('li'):
            a = li.find('a')
            href = a.get('href') if a else None
            if href:
                sub_units.append(WikiGroup(href[6:] if href.startswith('/wiki/') else href))
        return sub_units


class WikiSinger(WikiArtist):
    _category = 'singer'
    _member_rx = re.compile(
        r'^.* is (?:a|the) (.*?)(?:member|vocalist|rapper|dancer|leader|visual|maknae) of (.*?group) (.*)\.'
    )

    def __init__(self, uri_path=None, client=None, *, _member_of=None, **kwargs):
        super().__init__(uri_path, client, **kwargs)
        self.member_of = _member_of
        self.__check_associated = False
        if self._raw:
            clean_soup = self._clean_soup
            mem_match = self._member_rx.search(clean_soup.text.strip())
            if mem_match:
                if 'former' not in mem_match.group(1) and 'left the group' not in mem_match.group(2):
                    group_name = mem_match.group(3)
                    m = re.match(r'^(.*)\.\s+[A-Z]', group_name)
                    if m:
                        group_name = m.group(1)
                    # log.debug('{} appears to be a member of group {!r}; looking for group page...'.format(self, group_name))
                    for i, a in enumerate(clean_soup.find_all('a')):
                        if a.text and a.text in group_name:
                            href = (a.get('href') or '')[6:]
                            # log.debug('{}: May have found group match for {!r} => {!r}, href={!r}'.format(self, group_name, a.text, href))
                            if href and (href != self._uri_path):
                                try:
                                    self.member_of = WikiGroup(href, self._client)
                                except WikiTypeError as e:
                                    fmt = '{}: Found possible group match for {!r}=>{!r}, href={!r}, but {}; rx={}'
                                    log.debug(fmt.format(self, group_name, a.text, href, e, mem_match.groups()))
                                else:
                                    break
            else:
                self.__check_associated = True

            eng_first, eng_last, cjk_eng_first, cjk_eng_last = None, None, None, None
            birth_names = []
            _birth_name = self._side_info.get('birth_name', [])
            if _birth_name:
                if isinstance(_birth_name, str):
                    try:
                        birth_names.append(split_name(_birth_name))
                    except ValueError as e:
                        log.error('{}: Error splitting birth_name: {!r}'.format(self, _birth_name))
                        raise e
                else:
                    if isinstance(_birth_name[0], str):
                        birth_names.append(_birth_name)
                    else:
                        birth_names.extend(_birth_name)

            birth_names.append((self._side_info.get('birth name'), self._side_info.get('native name')))
            # log.info('birth_names: {}'.format(birth_names))
            if birth_names and not self.cjk_name and 'stage name' not in self._clean_soup.text:
                for _name in chain.from_iterable(birth_names):
                    # log.info('Examining birth name={!r}'.format(_name))
                    if _name and LangCat.categorize(_name) in LangCat.asian_cats:
                        self.cjk_name = _name
                        self.name = multi_lang_name(self.english_name, self.cjk_name)

            for eng, cjk in birth_names:
                if eng and cjk:
                    cjk_eng_last, cjk_eng_first = eng.split(maxsplit=1)
                    self._add_aliases((eng, cjk))
                elif eng and ' ' in eng:
                    eng_first, eng_last = eng.rsplit(maxsplit=1)
                    self._add_aliases((eng, eng_first))
                    self.__add_aliases(eng_first)
                elif cjk:
                    self._add_alias(cjk)

            if cjk_eng_first or cjk_eng_last:
                if eng_last:
                    eng_first = cjk_eng_first if eng_last == cjk_eng_last else cjk_eng_last
                    self._add_alias(eng_first)
                    self.__add_aliases(eng_first)
                else:
                    self._add_alias(cjk_eng_first)

            if cjk_eng_last:
                self._add_alias('{} {}'.format(cjk_eng_last, self.english_name))

            if self.english_name:
                self.__add_aliases(self.english_name)

    def _post_init(self):
        if self.__check_associated:
            for associated in self.associated_acts:
                if isinstance(associated, WikiGroup):
                    for href, member_name in associated._members():
                        if self._uri_path == href:
                            self.member_of = associated
                            break

    def __add_aliases(self, name):
        for c in ' -':
            if c in name:
                name_split = name.split(c)
                for k in ('', ' ', '-'):
                    joined = k.join(name_split)
                    if joined not in self.aliases:
                        self._add_alias(joined)

    @cached_property
    def birthday(self):
        if isinstance(self._client, DramaWikiClient):
            return self._profile.get('birthdate')
        return self._side_info.get('birth_date')

    def matches(self, other, *args, **kwargs):
        is_name_match = super().matches(other, *args, **kwargs)
        if is_name_match and isinstance(other, WikiSinger) and self.birthday and other.birthday:
            return self.birthday == other.birthday
        return is_name_match

    @cached_property
    def qualname(self):
        """Like an FQDN for artists - if this is a WikiSinger, include the group they are a member of"""
        try:
            member_of = self.member_of
        except AttributeError:
            pass
        else:
            if member_of:
                return '{} [{}]'.format(self.name, member_of.name)
        return self.name

    def _as_collab(self):
        collab_dict = {'artist': (self.english_name, self.cjk_name), 'artist_href': self._uri_path}
        try:
            group = self.member_of
        except AttributeError:
            pass
        else:
            if group:
                collab_dict.update(of_group=(group.english_name, group.cjk_name), group_href=group._uri_path)
        return collab_dict


class WikiSongCollection(WikiEntity):
    _category = ('album', 'soundtrack', 'collab/feature/single')
    _part_rx = re.compile(r'(?:part|code no)\.?\s*', re.IGNORECASE)
    _bonus_rx = re.compile(r'^(.*)\s+bonus tracks?$', re.IGNORECASE)

    def __init__(
        self, uri_path=None, client=None, *, disco_entry=None, album_info=None, artist_context=None,
        version_title=None, **kwargs
    ):
        super().__init__(uri_path, client, **kwargs)
        self._track_cache = {}
        self._discography_entry = disco_entry or {}
        self.english_name, self.cjk_name, self.stylized_name, self.aka, self._info = None, None, None, None, None
        self._album_info = album_info or {}
        self._albums = []
        self._primary_artist = None
        self._intended = None
        self._artist_context = artist_context
        self._track_lists = None
        if isinstance(self._client, DramaWikiClient) or kwargs.get('no_init'):
            return
        elif self._raw:
            self._albums = albums = self._client.parse_album_page(self._uri_path, self._clean_soup, self._side_info)
            artists = albums[0]['artists']
            try:
                artists_hrefs = list(filter(None, (a.get('artist_href') for a in artists)))
                artists_names = list(filter(None, (a.get('artist')[0] for a in artists)))
            except AttributeError as e:
                log.error('Error processing artists for {}: {}'.format(self.url, artists))
                raise e

            if len(albums) > 1:
                err_base = '{} contains both original+repackaged album info on the same page'.format(uri_path)
                if not (disco_entry or version_title):
                    msg = '{} - a discography entry is required to identify it'.format(err_base)
                    raise WikiEntityIdentificationException(msg)

                disco_entry = disco_entry or {}
                d_title = disco_entry.get('title') or version_title
                d_lc_title = d_title.lower()
                try:
                    d_artist_name, d_artist_uri_path = disco_entry.get('primary_artist')    # tuple(name, uri_path)
                except TypeError as e:
                    d_artist_name, d_artist_uri_path = None, None
                    d_no_artist = True
                else:
                    d_no_artist = False

                d_artist_name = d_artist_name[0] if isinstance(d_artist_name, (list, tuple)) else d_artist_name
                d_lc_artist = d_artist_name.lower() if d_artist_name else ''

                if d_no_artist or d_artist_uri_path in artists_hrefs or d_lc_artist in map(str.lower, artists_names):
                    for album in albums:
                        if d_lc_title in map(str.lower, map(str, album['title_parts'])):
                            self._album_info = album
                else:               # Likely linked as a collaboration
                    for package in self.packages:
                        for edition, disk, tracks in package.editions_and_disks:
                            for track in tracks:
                                track_name = track.long_name.lower()
                                if d_lc_title in track_name and d_lc_artist in track_name:
                                    fmt = 'Matched {!r} - {!r} to {} as a collaboration'
                                    log.debug(fmt.format(d_artist_name, d_title, package))
                                    self._album_info = package._album_info
                                    self._intended = edition, disk, track

                if not self._album_info:
                    msg = '{}, and it could not be matched with discography entry: {}'.format(err_base, disco_entry)
                    raise WikiEntityIdentificationException(msg)
            else:
                self._album_info = albums[0]

            self.english_name, self.cjk_name, self.stylized_name, self.aka, self._info = self._album_info['title_parts']
        elif disco_entry:
            self._primary_artist = disco_entry.get('primary_artist')
            if 'title_parts' in disco_entry:
                self.english_name, self.cjk_name, self.stylized_name, self.aka, self._info = disco_entry['title_parts']
            else:
                try:
                    try:
                        self.english_name, self.cjk_name = eng_cjk_sort(disco_entry['title'])
                    except ValueError as e1:
                        fmt = 'Unexpected disco_entry title for {}: {!r}; retrying'
                        log.log(5, fmt.format(self.url, disco_entry['title']))
                        self.english_name, self.cjk_name = split_name(disco_entry['title'], allow_cjk_mix=True)
                except Exception as e:
                    if not kwargs.get('no_fetch'):
                        log.error('Error processing disco entry title: {}'.format(e))
                    msg = 'Unable to find valid title in discography entry: {}'.format(disco_entry)
                    raise WikiEntityInitException(msg) from e
        else:
            msg = 'A valid uri_path / discography entry are required to initialize a {}'.format(type(self).__name__)
            raise WikiEntityInitException(msg)

        if self.english_name and ' : ' in self.english_name:
            self.english_name = self.english_name.replace(' : ', ': ')

        self._track_lists = self._album_info.get('track_lists')
        if self._track_lists is None:
            album_tracks = self._album_info.get('tracks')
            if not album_tracks:
                album_tracks = self._discography_entry.get('tracks')

            if album_tracks:
                self._track_lists = [album_tracks]

        if not self.cjk_name and self._track_lists:
            for track_list in self._track_lists:
                if self.cjk_name:   # May happen if multiple track lists exist
                    break
                for track in track_list.get('tracks', []):
                    try:
                        eng, cjk = track.get('name_parts')
                    except Exception as e:
                        pass
                    else:
                        if eng == self.english_name:
                            self.cjk_name = cjk
                            break

        if self._track_lists and disco_entry and self.english_name:
            d_title = disco_entry.get('title') or version_title
            # log.debug('Title from disco_entry={!r}'.format(d_title))
            d_lc_title = d_title.lower() if isinstance(d_title, str) else d_title[0].lower()
            if LangCat.categorize(d_lc_title) == LangCat.ENG and d_lc_title != self.english_name.lower():
                for track_list in self._track_lists:
                    section = track_list.get('section')
                    if isinstance(section, str) and section.lower() == d_lc_title:
                        self.english_name = section
                        self._intended = section, 1
                        break

        self.name = multi_lang_name(self.english_name, self.cjk_name)
        if self._info:
            self.name = ' '.join(chain((self.name,), map('({})'.format, self._info)))

        if self._raw and isinstance(self._client, KpopWikiClient) and not disco_entry and not artist_context:
            artist = None
            try:
                # log.debug('{}: {} Trying to access artist...'.format(self, self.url))
                artist = self.artist
            except NoPrimaryArtistError:
                try:
                    artist = self.artists[0]
                except IndexError:
                    pass
            finally:
                for key in ('artists', '_artists', 'artist'):
                    try:
                        del self.__dict__[key]
                    except KeyError:
                        pass

            if artist is not None:
                for album in artist.discography:
                    if album == self:
                        self._discography_entry = album._discography_entry
                        break

    def __lt__(self, other):
        comparison_type_check(self, other, WikiSongCollection, '<')
        return self.name < other.name

    def __gt__(self, other):
        comparison_type_check(self, other, WikiSongCollection, '>')
        return self.name > other.name

    def _additional_aliases(self):
        try:
            artist = self._artist_context or self.artist
        except Exception:
            return []
        else:
            return ['{} {}'.format(artist.english_name, a) for a in self._aliases()]

    @cached_property
    def _info_src(self):
        artist = self._artist_context
        return self.url if self.url else artist.url if artist and artist.url else self._primary_artist

    @cached_property
    def language(self):
        return self._discography_entry.get('language')

    @cached_property
    def released(self):
        return self._album_info.get('released')

    @cached_property
    def year(self):
        return self._discography_entry.get('year')

    @cached_property
    def _alt_version(self):
        try:
            artist = self.artist
        except NoPrimaryArtistError:
            pass
        else:
            try:
                alt_artist = artist.for_alt_site(KpopWikiClient._site)
            except Exception as e:
                pass
            else:
                return alt_artist.find_song_collection(self, allow_alt=False)
        return None

    @cached_property
    def _base_type(self):
        base_type = self._discography_entry.get('base_type')
        if isinstance(self._client, WikipediaClient):
            sub_type = self._discography_entry.get('sub_type')
            if base_type == 'albums':
                if sub_type == 'reissues':
                    base_type = 'repackage_albums'
                elif sub_type == 'compilation albums':
                    base_type = 'best_albums'
                else:
                    base_type = sub_type.replace(' ', '_')

        if base_type is None:
            return None

        base_type = base_type.replace(' ', '_')
        if not base_type.endswith('s'):
            base_type += 's'

        return base_type

    @cached_property
    def album_type(self):
        if self._base_type == 'extended_plays' and not isinstance(self._client, KpopWikiClient):
            alt_alb = self._alt_version     # This is for when the full track list is available elsewhere
            if alt_alb:
                return alt_alb.album_type

        try:
            return DISCOGRAPHY_TYPE_MAP[self._base_type]
        except KeyError as e:
            log.warning('{}: Unexpected album base_type: {!r}'.format(self, self._base_type))
            return 'UNKNOWN'

    @cached_property
    def album_num(self):
        if self._base_type == 'extended_plays' and not isinstance(self._client, KpopWikiClient):
            alt_alb = self._alt_version     # This is for when the full track list is available elsewhere
            if alt_alb:
                return alt_alb.album_num

        return self._discography_entry.get('num')

    @cached_property
    def num_and_type(self):
        lang = self._discography_entry.get('language')
        if lang and lang.lower() != 'korean':
            return '{} {} {}'.format(self.album_num, lang.title(), self.album_type)
        return '{} {}'.format(self.album_num, self.album_type)

    def title(self, hide_edition=False):
        extra = ' '.join(map('({})'.format, self._info)) if self._info else ''
        return '{} {}'.format(self.name, extra) if extra else self.name

    @cached()
    def expected_rel_dir(self, as_path=False, base_title=None, released=None, year=None, hide_edition=False):
        """
        :param bool as_path: Return a Path object instead of a string
        :param str base_title: Base title to use for editions/parts
        """
        base_title = base_title or self.title(hide_edition)
        numbered_type = self.album_type in ALBUM_NUMBERED_TYPES
        if numbered_type or self.album_type in ALBUM_DATED_TYPES:
            try:
                released = released or self.released
                release_str = released.strftime('%Y.%m.%d')
            except Exception:
                year = year or self.year
                release_str = year or ''
            release_date = '[{}] '.format(release_str) if release_str else ''

            title = '{}{}'.format(release_date, base_title)
            if numbered_type:
                suffix = ' [{}]'.format(self.num_and_type)
                if not title.endswith(suffix):
                    title += suffix
        else:
            title = base_title

        path = Path(self.album_type + 's').joinpath(sanitize_path(title))
        return path if as_path else path.as_posix()

    @cached()
    def expected_rel_path(self, true_soloist=False, base_title=None, released=None, year=None, hide_edition=False):
        rel_to_artist_dir = self.expected_rel_dir(True, base_title, released, year)
        artist = self.artist
        if artist._client and not isinstance(artist._client, KpopWikiClient):
            try:
                artist = artist.for_alt_site(KpopWikiClient._site)
            except Exception as e:
                pass
        if not true_soloist and isinstance(artist, WikiSinger) and artist.member_of:
            soloist = artist
            artist_dir = soloist.member_of.expected_rel_path()
            soloist_name = soloist.english_name or soloist.name
            if self.album_type == 'Soundtrack':
                d_name = sanitize_path('{} [{}]'.format(rel_to_artist_dir.name, soloist_name))
                rel_to_artist_dir = rel_to_artist_dir.with_name(d_name)
            else:
                group = soloist.member_of
                group_members_present = [a for a in self.artists if a in group]
                if len(group_members_present) > 1 and len(group_members_present) != len(self.artists):
                    rel_to_artist_dir = Path('Collaborations', rel_to_artist_dir.name)
                else:
                    rel_to_artist_dir = Path('Solo', sanitize_path(soloist_name), rel_to_artist_dir.name)
        else:
            artist_dir = artist.expected_rel_path()
        return artist_dir.joinpath(rel_to_artist_dir)

    def _has_no_valid_links(self, href, text):
        if not self._raw and self._artist_context:  # Created based on discography info
            return self._artist_context._has_no_valid_links(href, text)
        return super()._has_no_valid_links(href, text)

    def _find_href(self, texts, categories=None):
        if not self._raw and self._artist_context:  # Created based on discography info
            return self._artist_context._find_href(texts, categories)
        return super()._find_href(texts, categories)

    @cached_property
    def _artists(self):
        artists = OrderedDict()
        if self._primary_artist:
            primary = tuple(sorted(
                {'artist': eng_cjk_sort(self._primary_artist[0]), 'artist_href': self._primary_artist[1]}.items()
            ))
            artists[primary] = None

        d_collabs = self._discography_entry.get('collaborators', [])
        a_artists = self._album_info.get('artists', [])
        for artist in chain(a_artists, d_collabs):
            try:
                artists[tuple(sorted(artist.items()))] = None
            except Exception as e:
                fmt = '{}: Error processing artist={!r} from a_artists={!r} d_collabs={!r}'
                log.error(fmt.format(self, artist, a_artists, d_collabs))
                raise e

        artists = [dict(artist) for artist in artists]
        artist_map = OrderedDict()
        for artist in artists:
            artist_name = artist['artist']
            if artist_name in artist_map:
                current = artist_map[artist_name]
                for key, val in artist.items():
                    if current.get(key) is None and val is not None:
                        current[key] = val
            else:
                artist_map[artist_name] = artist
        return list(artist_map.values())

    def _get_artist(self, artist_dict, artists=None):
        # log.debug('{}: Processing artist: {}'.format(self, artist))
        name = artist_dict['artist']
        if name[0].lower() in ('various artists', 'various'):
            return None

        href = artist_dict.get('artist_href')
        of_group = artist_dict.get('of_group')
        # group_href = artist.get('group_href')
        if self._has_no_valid_links(href, name[0]):
            fmt = '{}: Skipping page search for artist={!r} of_group={!r} found on {} because it has a red link'
            log.log(5, fmt.format(self, name, of_group, self.url), extra={'color': 94})
            return WikiArtist(href, name=name, of_group=of_group, client=self._client, no_fetch=True)

        try:
            log.debug('{}: Looking for artist href={!r} name={!r} of_group={!r}'.format(self, href, name, of_group))
            return WikiArtist(href, name=name, of_group=of_group, client=self._client)
        except AmbiguousEntityException as e:
            # log.debug('{}: artist={} => ambiguous'.format(self, artist))
            if self._artist_context and isinstance(self._artist_context, WikiGroup):
                for member in self._artist_context.members:
                    if member._uri_path in e.alternatives:
                        return member

            fmt = '{}\'s artist={!r} is ambiguous'
            no_warn = False
            if e.alternatives:
                try:
                    return e.find_matching_alternative(WikiArtist, name, of_group, False, self._client)
                except AmbiguousEntityException:
                    pass

                fmt += ' - it could be one of: {}'.format(' | '.join(e.alternatives))
                if len(e.alternatives) == 1:
                    try:
                        alt_entity = WikiEntity(e.alternatives[0])
                    except Exception:
                        pass
                    else:
                        if not isinstance(alt_entity, WikiArtist):
                            fmt = '{}\'s artist={!r} has no page in {}; the disambiguation alternative was {}'
                            log.debug(fmt.format(self, name, alt_entity._client.host, alt_entity))
                            no_warn = True

            if not no_warn:
                log.log(19, fmt.format(self, name), extra={'color': (11, 9)})

            return WikiArtist(href, name=name, no_fetch=True, client=self._client)
        except CodeBasedRestException as e:
            # log.debug('{}: artist={} => {}'.format(self, artist, e))
            if isinstance(self._client, KpopWikiClient):
                try:
                    return WikiArtist(name=name, of_group=of_group)
                except CodeBasedRestException as e2:
                    fmt = 'Error retrieving info for {}\'s artist={!r} from multiple clients: {}'
                    log.debug(fmt.format(self, artist_dict, e), extra={'color': 13})
                    return WikiArtist(href, name=name, no_fetch=True)
            else:
                msg = 'Error retrieving info for {}\'s artist={!r}: {}'.format(self, artist_dict, e)
                if href is None:
                    log.log(9 if isinstance(self, WikiSoundtrack) else 10, msg)
                else:
                    log.error(msg, extra={'color': 13})
                return WikiArtist(href, name=name, no_fetch=True)
        except WikiTypeError as e:
            # log.debug('{}: artist={} => {}'.format(self, artist, e))
            log_lvl = logging.DEBUG if isinstance(self._client, WikipediaClient) else logging.WARNING
            if e.category == 'disambiguation':
                fmt = '{}\'s artist={!r} has an ambiguous href={}'
                log.log(log_lvl, fmt.format(self, name, e.url), extra={'color': (11, 9)})
            else:
                fmt = '{}\'s artist={!r} with href={!r} doesn\'t appear to be an artist: {}'
                log.log(log_lvl, fmt.format(self, name, href, e), extra={'color': (11, 9)})
                # raise e
            return WikiArtist(href, name=name, no_fetch=True)
        except WikiEntityInitException as e:
            #logging.DEBUG if not href and not self._find_href(name) else logging.ERROR
            artist_alias = next((a for a in artists if a.matches(name)), None) if artists else None
            if not artist_alias:
                msg = '{}: Unable to find artist={} found on {}: {}'.format(self, artist_dict, self._info_src, e)
                log.log(6 if isinstance(e, NoUrlFoundException) else logging.ERROR, msg, extra={'color': 9})
                return WikiArtist(href, name=name, no_fetch=True)
            else:
                fmt = '{}: Artists contained an alias={!r} for already known artist={}'
                log.debug(fmt.format(self, name, artist_alias))
        except Exception as e:
            msg = '{}: {} finding artist={} from {}: {}'.format(self, type(e).__name__, artist_dict, self._info_src, e)
            log.error(msg, extra={'color': 9})
            log.log(19, traceback.format_exc())
            return WikiArtist(href, name=name, no_fetch=True)
        return None

    @cached_property
    def artists(self):
        artists = set()
        for _artist in self._artists:
            artist = self._get_artist(_artist, artists)
            # log.debug('{}: artist={} => adding'.format(self, artist))
            if artist is not None:
                artists.add(artist)
        return sorted(artists)

    @cached_property
    def artist(self):
        artists = self.artists
        if len(artists) == 1:
            return artists[0]
        elif self._artist_context:
            return self._artist_context

        if self._raw and isinstance(self._client, (KpopWikiClient, WikipediaClient)):
            fmt = '{}: Examining side info for primary artist info from {} via client={}'
            log.debug(fmt.format(self, self.url, self._client))
            artists_raw = self._side_info.get('artist')
            if artists_raw and len(artists_raw) == 1:
                lc_artist_raw = artists_raw[0].lower()
                feat_indicators = ('feat. ', 'featuring ', 'with ')
                kw_idx = next((lc_artist_raw.index(val) for val in feat_indicators if val in lc_artist_raw), None)
                if kw_idx is not None:
                    before = artists_raw[0][:kw_idx].strip()
                    log.debug('{}: Trying to find primary artist from side info: {!r}'.format(self, before))
                    primary = {artist for artist in artists if artist.matches(before)}
                    if len(primary) == 1:
                        return primary.pop()
                    else:
                        fmt = '{}: Unable to determine primary artist based on side info - pre-feat matches: {}'
                        log.debug(fmt.format(self, primary))

        raise NoPrimaryArtistError('{} has multiple contributing artists and no artist context'.format(self))

    @cached_property
    def collaborators(self):
        artists = self.artists
        try:
            primary = self.artist
        except NoPrimaryArtistError:
            primary = None

        if len(artists) < 2:
            return []
        elif primary:
            return [artist for artist in artists if artist != primary]
        else:
            return artists

    @cached_property
    def _editions_by_disk(self):
        editions_by_disk = defaultdict(list)
        for track_section in self._track_lists:
            disk = track_section.get('disk')
            if disk is not None:
                try:
                    disk = int(disk)
                except Exception:
                    pass
            editions_by_disk[disk].append(track_section)
        return editions_by_disk

    @cached_property
    def has_multiple_disks(self):
        return len(set(p.disk for p in self.parts)) > 1

    def _get_tracks(self, edition_or_part=None, disk=None):
        if disk is not None:
            try:
                disk = int(disk)
            except Exception:
                pass
        if self._track_lists:
            # log.debug('{}: Retrieving tracks for edition_or_part={!r}'.format(self, edition_or_part))
            if disk is None and edition_or_part is None or isinstance(edition_or_part, int):
                edition_or_part = edition_or_part or 0
                try:
                    return self._track_lists[edition_or_part]
                except IndexError as e:
                    msg = '{} has no part/edition called {!r}'.format(self, edition_or_part)
                    raise InvalidTrackListException(msg) from e

            editions = self._editions_by_disk[disk or 1]
            if not editions and disk is None:
                editions = self._editions_by_disk[disk]
            if not editions:
                raise InvalidTrackListException('{} has no disk {!r}'.format(self, disk))
            elif edition_or_part is None:
                return editions[0]

            # noinspection PyUnresolvedReferences
            lc_ed_or_part = edition_or_part.lower()
            is_part = lc_ed_or_part.startswith(('part', 'code no'))
            if is_part:
                lc_ed_or_part = self._part_rx.sub('part ', lc_ed_or_part)

            bonus_match = None
            for i, edition in enumerate(editions):
                section = edition.get('section') or ''
                if section and not isinstance(section, str):
                    section = section[0]
                name = section.lower()
                if name == lc_ed_or_part or (is_part and lc_ed_or_part in self._part_rx.sub('part ', name)):
                    return edition
                else:
                    m = self._bonus_rx.match(name)
                    if m and m.group(1).strip() == lc_ed_or_part:
                        bonus_match = i
                        # log.debug('bonus_match={}: {}'.format(bonus_match, edition))
                        break

            if bonus_match is not None:
                edition = editions[bonus_match]
                first_track = min(t['num'] for t in edition['tracks'])
                if first_track == 1:
                    return edition
                name = self._bonus_rx.match(edition['section']).group(1).strip()
                combined = {
                    'section': name, 'tracks': edition['tracks'].copy(), 'disk': edition.get('disk'),
                    'links': edition.get('links', [])
                }

                combos = edition_combinations(editions[:bonus_match], first_track)
                # log.debug('Found {} combos'.format(len(combos)))
                if len(combos) != 1:
                    # for combo in combos:
                    #     tracks = sorted(t['num'] for t in chain.from_iterable(edition['tracks'] for edition in combo))
                    #     log.debug('Combo: {} => {}'.format(', '.join(repr(e['section']) for e in combo), tracks))
                    raise InvalidTrackListException('{}: Unable to reconstruct {!r}'.format(self, name))

                for edition in combos[0]:
                    combined['tracks'].extend(edition['tracks'])
                    combined['links'].extend(edition.get('links', []))

                combined['tracks'] = sorted(combined['tracks'], key=lambda t: t['num'])
                combined['links'] = sorted(set(combined['links']))
                return combined
            raise InvalidTrackListException('{} has no part/edition called {!r}'.format(self, edition_or_part))
        else:
            if 'single' in self.album_type.lower():
                return {'tracks': [{'name_parts': (self.english_name, self.cjk_name)}]}
            else:
                fmt = '{}: No page content found for {} - returning empty track list'
                log.log(9, fmt.format(self._client.host, self), extra={'color': 8})
                return {'tracks': []}

    @cached('_track_cache', exc=True)
    def get_tracks(self, edition_or_part=None, disk=None):
        # log.debug('{}.get_tracks({!r}, {!r}) called'.format(self, edition_or_part, disk), extra={'color': 76})
        if self._intended is not None and edition_or_part is None and disk is None:
            if len(self._intended) == 3:    # edition, disk, track
                # noinspection PyTupleAssignmentBalance
                edition_or_part, disk, track_info = self._intended
                return [
                    WikiTrack(track_info, part, self._artist_context)
                    for (part_ed, part_disk, lang), part in self._parts.items()
                    if edition_or_part == part_ed and disk == part_disk
                ]
            elif len(self._intended) == 2:
                # noinspection PyTupleAssignmentBalance
                edition_or_part, disk = self._intended

        parts = self.parts_for(edition_or_part, disk)
        if not parts:
            fmt = 'Unable to find part of {} for edition_or_part={!r}, disk={!r} from {}'
            raise InvalidTrackListException(fmt.format(self, edition_or_part, disk, self._info_src))

        lang = self.language or 'Korean'
        return [t for p in parts for t in p.get_tracks() if p.language == lang]

    @cached_property
    def editions_and_disks(self):
        bonus_rx = re.compile('^(.*)\s+bonus tracks?$', re.IGNORECASE)
        editions = []
        if self._track_lists:
            for edition in self._track_lists:
                section = edition.get('section')
                if section and not isinstance(section, str):
                    section = section[0]
                try:
                    m = bonus_rx.match(section or '')
                except TypeError as e:
                    log.error('{}: Unexpected section value in {}: {}'.format(self, self.url, section))
                    raise e
                name = m.group(1).strip() if m else section
                disk = edition.get('disk')
                editions.append((name, disk, self.get_tracks(name, disk)))
        return editions

    @cached_property
    def packages(self):
        if len(self._albums) == 1:
            return [self]
        elif len(self._artists) > 1:
            fmt = 'Packages can only be retrieved for {} objects with 1 packaging or a primary artist'
            fmt += '; {}\'s artists: {}'
            raise AttributeError(fmt.format(type(self).__name__, self, self._artists))

        try:
            artist = self._artists[0]['artist']
        except Exception as e:
            _artist = self.artist
            artist = tuple(sorted({'artist': _artist.name_tuple, 'artist_href': _artist._uri_path}.items()))
            # log.error('Unable to get artist from {} / {}'.format(self, self._artists))
            # raise e

        packages = []
        for album in self._albums:
            disco_entry = {'title': album['title_parts'][0], 'artist': artist}
            tmp = WikiSongCollection(self._uri_path, self._client, disco_entry=disco_entry)
            packages.append(tmp)
        return packages

    @cached_property
    def _parts(self):
        parts = OrderedDict()
        bonus_rx = re.compile('^(.*)\s+bonus tracks?$', re.IGNORECASE)
        if self._track_lists is None:
            parts[(None, None)] = WikiSongCollectionPart(self, None, None, self.language, None, self._get_tracks())
        else:
            for track_list in self._track_lists:
                section = track_list.get('section')
                language = track_list.get('language') or self.language
                if section and not isinstance(section, str):
                    section = tuple(filter(None, section))
                    _section0 = section[0]
                    _section = ' - '.join(section)
                else:
                    _section0 = _section = section

                try:
                    m = bonus_rx.match(_section or '')
                except TypeError as e:
                    log.error('{}: Unexpected section value in {}: {}'.format(self, self.url, section))
                    raise e

                name = m.group(1).strip() if m else _section
                disk = track_list.get('disk')
                if disk is not None:
                    try:
                        disk = int(disk)
                    except Exception:
                        pass

                _tracks = self._get_tracks(_section0, disk)
                parts[(name, disk, language)] = WikiSongCollectionPart(self, name, disk, language, section, _tracks)

            if len(self._track_lists) != len(parts):
                fmt = 'Album part name conflict found for {}: found {} track lists but {} parts'
                raise WikiAlbumPartProcessingError(fmt.format(self, len(self._track_lists), len(parts)))

        return parts

    @cached_property
    def parts(self):
        try:
            return list(self._parts.values())
        except WikiAlbumPartProcessingError as e:
            log.log(19, str(e))
            log.log(19, traceback.format_exc())
            return []

    def parts_for(self, edition_or_part=None, disk=None):
        if not self._track_lists:
            return self.parts

        if disk is None:
            parts = self.parts
        else:
            try:
                disk = int(disk)
            except Exception:
                pass
            parts = [p for p in self.parts if p.disk == disk]

        if edition_or_part is None:
            return parts

        lc_ed_or_part = edition_or_part.lower()
        is_ost_part = lc_ed_or_part.startswith(('part', 'code no'))
        if is_ost_part:
            lc_ed_or_part = self._part_rx.sub('part ', lc_ed_or_part)

        filtered = []
        for part in parts:
            name = part.edition.lower() if part.edition else part.edition
            if name == lc_ed_or_part or (name and is_ost_part and lc_ed_or_part in self._part_rx.sub('part ', name)):
                filtered.append(part)
        return filtered

    @cached_property
    def _part_track_counts(self):
        track_counts = set()
        for part in self.parts:
            tracks = part.get_tracks()
            track_count = len(tracks)
            track_counts.add(track_count)
            for track in tracks:
                if track.misc and any(' only' in m for m in track.misc):
                    track_count -= 1
            track_counts.add(track_count)

        if len(track_counts) == 1 and 0 in track_counts:
            return None
        return track_counts

    def find_track(self, name, min_score=75, include_score=False, *, edition_or_part=None, disk=None, **kwargs):
        match_fmt = '{}: {} matched {!r} with score={} because its alias={!r} =~= {!r}'
        best_score, best_alias, best_val, best_track = 0, None, None, None
        normalized = WikiTrack._normalize_for_matching(name)
        try:
            tracks = self.get_tracks(edition_or_part, disk)
        except InvalidTrackListException:
            pass
        else:
            for track in tracks:
                # log.debug('{}: Comparing {} to normalized={!r}'.format(self, track, normalized))
                score, alias, val = track.score_match(normalized, normalize=False, disk=disk, **kwargs)
                if score >= 100:
                    # log.debug(match_fmt.format(self, track, name, score, alias, val))
                    return (track, score) if include_score else track
                elif score > best_score:
                    best_score, best_alias, best_val, best_track = score, alias, val, track

        if best_score > min_score:
            if best_score < 95:
                log.debug(match_fmt.format(self, best_track, name, best_score, best_alias, best_val))
            return (best_track, best_score) if include_score else best_track
        return (None, -1) if include_score else None

    def find_part(self, track_tuples, min_score=75, include_score=False, disk=None, **kwargs):
        if disk is not None:
            try:
                disk = int(disk)
            except Exception:
                pass
        best_score, best_part = 0, None
        parts = self.parts if disk is None else [p for p in self.parts if p.disk == disk]
        # log.debug('{} has parts with matching disk: {}'.format(self, parts))
        # log.debug(' > Comparing parts to tracks: {}'.format(track_tuples))

        for part in parts:
            if len(part.get_tracks()) * 2 < len(track_tuples):
                continue
            part_scores = []
            for track_name, track_num in track_tuples:
                # log.debug('Searching part={} for track name={!r} num={}'.format(part, track_name, track_num))
                track, score = part.find_track(track_name, min_score=min_score, include_score=True, disk=disk, **kwargs)
                part_scores.append(score)

            part_score = int(sum(part_scores) / len(part_scores)) if part_scores else 0
            if len(part) != len(track_tuples):
                part_score -= 30

            # log.debug('Part={} score={} for: {}'.format(part, part_score, ', '.join(t[0] for t in track_tuples)))
            if part_score > best_score:
                best_score, best_part = part_score, part

        if best_score > min_score:
            return (best_part, best_score) if include_score else best_part
        return (None, -1) if include_score else None

    def score_match(self, other, *args, **kwargs):
        if isinstance(other, str):
            rom_num = next((rn for rn in ROMAN_NUMERALS if other.endswith(' ' + rn)), None)
            if rom_num is not None:
                alt_other = re.sub(r'\s+{}$'.format(rom_num), ' {}'.format(ROMAN_NUMERALS[rom_num]), other)
                other = (other, alt_other)
        return super().score_match(other, *args, **kwargs)

    @cached_property
    def contains_mixed_editions(self):
        try:
            tracks = self.get_tracks()
        except Exception as e:
            return False
        return any(t._edition_specific for t in tracks) and not all(t._edition_specific for t in tracks)


class WikiSongCollectionPart:
    _part_rx = re.compile(r'((?:part|code no)\.?\s*\d+)', re.IGNORECASE)
    passthru_attrs = {
        'released', 'year', 'album_type', 'album_num', 'num_and_type', '_artists', 'artists', 'artist', 'collaborators'
        'english_name', 'cjk_name'
    }

    def __init__(self, collection, edition, disk, language, section_info, track_list):
        self._track_cache = {}
        self._collection = collection
        self._section_info = (section_info,) if isinstance(section_info, str) else section_info
        self._track_list = track_list
        self.edition = edition
        self.disk = disk
        self.language = language

        # self.english_name = collection.english_name
        # self.cjk_name = collection.cjk_name
        self._info = collection._info

        if self.cjk_name and self.language and LangCat.categorize(self.cjk_name) != LangCat.for_name(self.language):
            _tracks = self._get_tracks()
            for track in _tracks.get('tracks', []):
                try:
                    eng, cjk = track.get('name_parts')
                except Exception as e:
                    pass
                else:
                    if eng == self.english_name:
                        self.cjk_name = cjk
                        break

    @property
    def name(self):
        name = multi_lang_name(self.english_name, self.cjk_name)
        if self._info:
            return ' '.join(chain((name,), map('({})'.format, self._info)))
        return name

    def __repr__(self):
        return '<{}({!r})>'.format(type(self).__name__, self.title())

    def __getattr__(self, item):
        # if item in self.passthru_attrs:
        return getattr(self._collection, item)
        # raise AttributeError('{} has no attribute {!r}'.format(type(self).__name__, item))

    def __iter__(self):
        yield from self.get_tracks()

    def __len__(self):
        return len(self._track_list['tracks'])

    @cached()
    def title(self, hide_edition=False, lang=None):
        extra = ' '.join(map('({})'.format, self._info)) if self._info else ''
        name = self.name if lang is None else getattr(self, '{}_name'.format(lang))
        title = '{} {}'.format(name, extra) if extra else name
        if self.edition:
            if self.language and self.language.lower() in self.edition.lower():
                pass
            else:
                m = self._part_rx.search(self.edition)
                if m:
                    title += ' - {}'.format(m.group(1).strip())
                elif isinstance(self._collection, WikiSoundtrack) and self.edition in self.name:
                    pass    # Make no changes - this is the full OST
                elif not hide_edition:
                    title += ' - {}'.format(self.edition)

        if self.language and self.language.lower() != 'korean' and not hide_edition:
            title += ' ({} ver.)'.format(self.language)
        return title

    def titles(self, hide_edition=False):
        for lang in (None, 'english', 'cjk'):
            try:
                yield self.title(hide_edition, lang)
            except Exception as e:
                pass

    @cached_property
    def released(self):
        if not isinstance(self._collection._client, DramaWikiClient):
            return self._collection.released
        return self._track_list['info']['release date']

    @cached_property
    def year(self):
        if not isinstance(self._collection._client, DramaWikiClient):
            return self._collection.year
        return self.released.year

    def _get_tracks(self):
        return self._track_list

    @cached('_track_cache', exc=True)
    def get_tracks(self):
        artist_context = self._collection._artist_context
        tracks = [WikiTrack(info, self, artist_context) for info in self._track_list['tracks']]
        for track in tracks:
            if track.is_inst and (not track.english_name or not track.cjk_name):
                for _track in tracks:
                    if _track is not track and _track.english_name and _track.cjk_name:
                        eng_and_no_cjk = track.english_name == _track.english_name and not track.cjk_name
                        cjk_and_no_eng = track.cjk_name == _track.cjk_name and not track.english_name
                        if eng_and_no_cjk or cjk_and_no_eng:
                            track.update_name(_track.english_name, _track.cjk_name, False)
        return tracks

    def expected_rel_dir(self, as_path=False, hide_edition=False):
        return self._collection.expected_rel_dir(as_path, self.title(hide_edition), self.released, self.year)

    def expected_rel_path(self, true_soloist=False, hide_edition=False):
        return self._collection.expected_rel_path(true_soloist, self.title(hide_edition), self.released, self.year)

    def find_track(self, name, min_score=75, include_score=False, edition_or_part=None, disk=None, **kwargs):
        if edition_or_part not in (None, self.edition) and disk not in (None, self.disk):
            return (None, -1) if include_score else None
        return self._collection.find_track(
            name, min_score, include_score, edition_or_part=self.edition, disk=self.disk, **kwargs
        )

    @cached_property
    def contains_mixed_editions(self):
        tracks = self.get_tracks()
        return any(t._edition_specific for t in tracks) and not all(t._edition_specific for t in tracks)


class WikiAlbum(WikiSongCollection):
    _category = 'album'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        repackage_title = self._album_info.get('repackage_of_title')
        if self.name == repackage_title:
            self.name += ' (Repackage)'
            self.english_name += ' (Repackage)'

    def _aliases(self):
        aliases = super()._aliases()
        if self.repackage_of:
            for alias in list(aliases):
                if 'repackage' not in alias.lower():
                    aliases.add('{} (Repackage)'.format(alias))
        return aliases

    @cached_property
    def num_and_type(self):
        base = super().num_and_type
        return '{} Repackage'.format(base) if self.repackage_of else base

    @cached_property
    def repackaged_version(self):
        title = self._album_info.get('repackage_title')
        href = self._album_info.get('repackage_href')
        if href:
            return WikiAlbum(href, client=self._client, version_title=title)
        return None

    @cached_property
    def repackage_of(self):
        title = self._album_info.get('repackage_of_title')
        href = self._album_info.get('repackage_of_href')
        if href:
            return WikiAlbum(href, client=self._client, version_title=title)
        return None


class WikiSoundtrack(WikiSongCollection):
    _category = 'soundtrack'
    _ost_name_rx = re.compile(r'^(.* OST)\s*-?\s*((?:part|code no)\.?\s*\d+)$', re.IGNORECASE)
    _ost_name_paren_rx = re.compile(r'^(.*) \(.*\) OST$', re.IGNORECASE)
    _ost_simple_rx = re.compile(r'^(.* OST)', re.IGNORECASE)
    _mix_part_rx = re.compile(r'(.*OST)\s*\((.*OST)\) - (.*)', re.IGNORECASE)
    _search_filters = []

    def __init__(self, uri_path=None, client=None, **kwargs):
        super().__init__(uri_path, client, **kwargs)
        if isinstance(self._client, DramaWikiClient):
            if self._raw:
                self._track_lists = parse_ost_page(self._uri_path, self._clean_soup, client)
                self._album_info = {
                    'track_lists': self._track_lists, 'num': None, 'type': 'OST', 'repackage': False, 'length': None,
                    'released': None, 'links': []
                }
                part_1 = self._track_lists[0]
                eng, cjk = part_1['info']['title']

                try:
                    eng, cjk = (self._ost_name_rx.match(val).group(1).strip() for val in (eng, cjk))
                except Exception as e:
                    try:
                        eng, cjk = (self._ost_simple_rx.match(val).group(1).strip() for val in (eng, cjk))
                    except Exception as e1:
                        log.debug('OST @ {!r} had unexpected name: {!r} / {!r}'.format(self._uri_path, eng, cjk))
                    # raise WikiEntityInitException('Unexpected OST name for {}'.format(self._uri_path)) from e
                self.english_name, self.cjk_name = eng, cjk
                self.name = multi_lang_name(self.english_name, self.cjk_name)
                try:
                    tv_series = self.tv_series
                except AttributeError:
                    pass
                else:
                    self._add_aliases(('{} OST'.format(a) for a in tv_series.aliases))
            else:
                self._track_lists = []
                self._album_info = {
                    'track_lists': self._track_lists, 'num': None, 'type': 'OST', 'repackage': False, 'length': None,
                    'released': None, 'links': []
                }

        if self._discography_entry:
            m = self._ost_name_rx.match(self._discography_entry.get('title', ''))
            if m:
                self._intended = m.group(2).strip(), None
                if not isinstance(self._client, DramaWikiClient) or not self._raw:
                    title = m.group(1).strip()
                    try:
                        self.english_name, self.cjk_name = eng_cjk_sort(title)
                    except ValueError as e1:
                        log.log(5, 'Unexpected disco_entry title for {}: {!r}; retrying'.format(self, title))
                        self.english_name, self.cjk_name = split_name(title)
                    self.name = multi_lang_name(self.english_name, self.cjk_name)

    def _additional_aliases(self):
        addl_aliases = set(super()._additional_aliases())
        addl_aliases.update(chain.from_iterable(p.titles() for p in self.parts))
        try:
            addl_aliases.update(e[0] for e in self.editions_and_disks)
        except InvalidTrackListException:   # Happens when this obj was constructed from disco info
            pass

        try:
            tv_series = self.tv_series
        except AttributeError:
            return addl_aliases
        log.debug('{}: found self.tv_series: {}'.format(self, tv_series))

        all_aliases = self._aliases()
        all_aliases.update(addl_aliases)
        for i, show_alias in enumerate(tv_series.aliases):
            log.debug('{}: processing show_alias={!r} [{}]'.format(self, show_alias, i))
            if not any(show_alias in a for a in all_aliases):
                addl_aliases.add(show_alias + ' OST')

        return addl_aliases

    @classmethod
    def _pre_match_prep(cls, other):
        if isinstance(other, str):
            m0 = cls._mix_part_rx.match(other)
            if m0:
                lang_a, lang_b, part = m0.groups()
                other = (
                    other, lang_a, lang_b, '{} {}'.format(lang_a, part), '{} {}'.format(lang_b, part),
                    '{} ({})'.format(lang_a, lang_b)
                )
                # log.debug('other: {}'.format(other))
            else:
                m1 = cls._ost_name_rx.match(other)
                if m1:
                    title1 = m1.group(1)
                    if title1.endswith(' -'):
                        title1 = title1[:-1].strip()

                    m2 = cls._ost_name_paren_rx.match(title1)
                    if m2:
                        title2 = '{} OST'.format(m2.group(1).strip())
                        other = (other, title1, title2)
                    else:
                        other = (other, title1)
        return other

    def score_match(self, other, *args, **kwargs):
        if isinstance(other, str):
            other = self._pre_match_prep(other)
        # log.debug('{}: Comparing to: {}'.format(self, other))
        return super().score_match(other, *args, **kwargs)

    @cached_property
    def album_type(self):
        return 'Soundtrack'

    @cached_property
    def tv_series(self):
        if not isinstance(self._client, DramaWikiClient):
            raise AttributeError('{} has no attribute tv_series'.format(self))

        li = self._clean_soup.find(lambda tag: tag.name == 'li' and tag.text.startswith('Title:'))
        if li:
            a = li.find('a')
            if a:
                href = a.get('href')
                if href:
                    return WikiTVSeries(href, client=self._client)
        raise AttributeError('{} has no attribute tv_series'.format(self))

    @cached_property
    def _artists(self):
        if not isinstance(self._client, DramaWikiClient):
            return super()._artists

        artists = defaultdict(dict)
        keys = ('eng', 'cjk', 'group_eng', 'group_cjk', 'artist_href', 'group_href')
        for track_section in self._track_lists:
            for _artist in track_section['info']['artist']:
                eng, cjk = _artist['artist']
                artist_href = _artist.get('artist_href')
                group_href = _artist.get('group_href')
                try:
                    group_eng, group_cjk = _artist['of_group']
                except KeyError:
                    group_eng, group_cjk = None, None
                except Exception as e:
                    log.error('{}: Error processing artist of_group: {}'.format(self, _artist))
                    raise e
                # log.debug('Processing artist: {}'.format(', '.join('{}={!r}'.format(k, v) for k, v in zip(keys, (eng, cjk, group_eng, group_cjk, artist_href, group_href)))))
                for key, val in zip(keys, (eng, cjk, group_eng, group_cjk, artist_href, group_href)):
                    if val:
                        artists[eng].setdefault(key, val)

        fixed_artists = []
        for a in artists.values():
            group = None
            if any(k in a for k in ('group_eng', 'group_cjk')):
                group = (a.get('group_eng', ''), a.get('group_cjk', ''))
            fixed_artists.append({
                'artist_href': a.get('artist_href'), 'artist': (a.get('eng', ''), a.get('cjk', '')),
                'group_href': a.get('group_href'), 'of_group': group
            })
        return fixed_artists

    def _get_artist(self, artist_dict, artists=None):
        if not isinstance(self._client, DramaWikiClient):
            return super()._get_artist(artist_dict, artists)
        # log.debug('Processing artist: {!r}'.format(artist_dict), extra={'color': (1, 8)})
        eng, cjk = artist_dict['artist']
        if eng.lower() == 'various artists':
            return None

        aliases = (eng, cjk)
        try:
            group_eng, group_cjk = artist_dict.get('of_group')
        except Exception:
            group_eng, group_cjk = None, None
        if not group_eng and eng and cjk and LangCat.categorize(cjk) in LangCat.asian_cats and not self._find_href(aliases):
            # Don't bother looking up solo artists that have no (valid) links on this page
            eng_lc_nospace = ''.join(eng.split()).lower()
            if matches_permutation(eng_lc_nospace, cjk):
                # log.debug('No lookup being done for {!r}'.format(parts))
                return WikiArtist(aliases=aliases, no_fetch=True)
            # permutations = romanized_permutations(cjk)
            # log.debug('Comparing {!r} to: {}'.format(eng_lc_nospace, permutations))
            # if any(''.join(p.split()) == eng_lc_nospace for p in permutations):
                # log.debug('No lookup being done for {!r}'.format(parts))
                # return WikiArtist(aliases=aliases, no_fetch=True)
        try:
            try:
                return WikiArtist(aliases=aliases, of_group=group_eng)
            except WikiTypeError as e:
                if group_eng:
                    return WikiArtist(aliases=aliases)
                else:
                    raise e
        except AmbiguousEntityException as e:
            d_artist_href = artist_dict.get('artist_href')
            if d_artist_href:
                d_artist = WikiArtist(d_artist_href, client=self._client)
                if e.alternatives:
                    alternatives = []
                    _alts = list(e.alternatives)
                    for alt_href in e.alternatives:
                        if 'singer' in alt_href:
                            _alts.remove(alt_href)
                            alternatives.append(alt_href)
                    alternatives.extend(_alts)
                else:
                    alternatives = e.alternatives

                for i, alt_href in enumerate(alternatives):
                    if i > 3:
                        fmt = '{}: Skipping alt href comparison for {} =?= {} because it has too many alternatives'
                        log.warning(fmt.format(self, d_artist, alt_href))
                    else:
                        client = WikiClient.for_site(e.site) if e.site else None
                        tmp_artist = WikiArtist(alt_href, client=client)
                        if tmp_artist.matches(d_artist):
                            log.debug('{}: Matched {} to {}'.format(self, d_artist, tmp_artist))
                            return tmp_artist
                        else:
                            log.debug('{}: {} != {}'.format(self, d_artist, tmp_artist))
                else:
                    fmt = '{}\'s artist={!r} is ambiguous'
                    if e.alternatives:
                        fmt += ' - it could be one of: {}'.format(' | '.join(e.alternatives))
                    log.log(19, fmt.format(self, eng, group_eng), extra={'color': (11, 9)})
                    return WikiArtist(name=eng, no_fetch=True)
            else:
                fmt = '{}\'s artist={!r} is ambiguous'
                if e.alternatives:
                    fmt += ' - it could be one of: {}'.format(' | '.join(e.alternatives))
                log.warning(fmt.format(self, eng), extra={'color': (11, 9)})
                return WikiArtist(name=eng, no_fetch=True)
        except CodeBasedRestException as e:
            if e.code == 404:
                artist_href = artist_dict.get('artist_href')
                if artist_href:
                    fmt = 'No page found for {}\'s artist={!r} via client={}, but a {} link was found'
                    log.log(6, fmt.format(self, artist_dict, KpopWikiClient(), self._client))
                    try:
                        return WikiArtist(artist_href, client=self._client, of_group=group_eng)
                    except Exception as e1:
                        fmt = '{}: Unexpected {} using artist_href={} for {} found on {}: {}'
                        log.error(fmt.format(self, type(e1).__name__, artist_href, artist_dict, self._info_src, e1))
                else:
                    log.debug('No page found for {}\'s artist={!r}'.format(self, artist_dict))
            else:
                fmt = 'Error retrieving info for {}\'s artist={}: {}'
                log.error(fmt.format(self, artist_dict, e), extra={'color': 13})
            return WikiArtist(aliases=aliases, no_fetch=True)
        except (WikiEntityInitException, WikiEntityIdentificationException) as e:
            msg = 'Error retrieving info for {}\'s artist={}: {}'.format(self, artist_dict, e)
            artist_href = artist_dict.get('artist_href')
            if artist_href:
                log.log(6, msg + ', but a {} link was found'.format(self._client))
                try:
                    return WikiArtist(artist_href, client=self._client, of_group=group_eng)
                except Exception as e1:
                    fmt = '{}: Unexpected {} using artist_href={} for {} found on {}: {}'
                    log.error(fmt.format(self, type(e1).__name__, artist_href, artist_dict, self._info_src, e1))
            else:
                log.debug(msg, extra={'color': 13})
            return WikiArtist(aliases=aliases, no_fetch=True)
        except Exception as e:
            fmt = 'Unexpected error processing {}\'s artist={!r}: {}\n{}'
            log.error(fmt.format(self, artist_dict, e, traceback.format_exc()), extra={'color': (11, 9)})
        return None

    def _get_tracks(self, edition_or_part=None, disk=None):
        track_info = self._discography_entry.get('track_info')
        use_discography_info = self._intended is None and track_info
        if not use_discography_info and self._raw and self._track_lists:
            log.log(1, 'Skipping WikiSoundtrack _get_tracks({!r}, {!r}) for {}'.format(edition_or_part, disk, self.url))
            return super()._get_tracks(edition_or_part, disk)

        if track_info:
            _tracks = (track_info,) if isinstance(track_info, dict) else track_info
            tracks = []
            for _track in _tracks:
                track = _track.copy()
                track['collaborators'] = strify_collabs(track.get('collaborators') or [])
                misc = track.get('misc') or []
                if self._info:
                    misc.extend(self._info)
                track['misc'] = misc
                track['from_discography_info'] = True
                tracks.append(track)

            return {'tracks': tracks}
        else:
            fmt = '{}: No page content found for {} - returning empty track list'
            log.log(9, fmt.format(self._client.host, self), extra={'color': 8})
            return {'tracks': []}

    @cached()
    def expected_rel_path(self, true_soloist=False, base_title=None, released=None, year=None, hide_edition=False):
        try:
            artist = self.artist
        except NoPrimaryArtistError:
            return Path('Various Artists').joinpath(self.expected_rel_dir(True, base_title))
        else:
            return super().expected_rel_path(true_soloist, base_title, released, year)


class WikiFeatureOrSingle(WikiSongCollection):
    _category = 'collab/feature/single'

    def _get_tracks(self, edition_or_part=None, disk=None):
        if self._raw and self._track_lists and not self._album_info.get('fake_track_list'):
            _tracks = super()._get_tracks(edition_or_part, disk)['tracks']
            tracks = self.__update_tracks(_tracks)
        else:
            track_info = self._discography_entry.get('track_info')
            if track_info and not self._raw:
                # log.debug('{}: Using discography track info'.format(self))
                _tracks = (track_info,) if isinstance(track_info, dict) else track_info
                tracks = self.__update_tracks(_tracks, True)
            else:   # self._raw exists, but it had no track list
                single = None
                if self._track_lists:
                    # log.debug('{}: Using album page track info'.format(self))
                    single = self._track_lists[0]['tracks'][0]
                if not single:
                    # log.debug('{}: Using side bar track info'.format(self))
                    single = {'name_parts': (self.english_name, self.cjk_name), 'num': 1, 'misc': self._info}

                self.__dict__['_part_track_counts'] = {1, 2}
                single['collaborators'] = [a._as_collab() for a in self.collaborators]
                inst = single.copy()
                inst['version'] = 'Inst.'
                inst['num'] = 2
                tracks = [single, inst]
        return {'tracks': tracks}

    def __update_tracks(self, _tracks, incl_info=False):
        tracks = []
        album_collabs = [a._as_collab() for a in self.collaborators]
        for _track in _tracks:
            track = _track.copy()
            collabs = album_collabs.copy()
            track_collabs = (
                collab if isinstance(collab, dict) else {'artist': collab}
                for collab in (track.get('collaborators') or [])
            )
            collabs.extend(track_collabs)
            track['collaborators'] = collabs
            if incl_info:
                misc = track.get('misc') or []
                if self._info:
                    misc.extend(self._info)
                track['misc'] = misc
            tracks.append(track)
        return tracks


class WikiTrack(WikiMatchable):
    _category = '__track__'
    __feat_rx = re.compile(r'\((?:with|feat\.?|featuring)\s+(.*?)\)', re.IGNORECASE)
    disk = DictAttrProperty('_info', 'disk', type=int, default=1)
    num = DictAttrProperty('_info', 'num', type=lambda x: x if x is None else int(x), default=None)
    length_str = DictAttrProperty('_info', 'length', default='-1:00')
    language = DictAttrProperty('_info', 'language', default=None)
    version = DictAttrProperty('_info', 'version', default=None)
    misc = DictAttrProperty('_info', 'misc', default=None)
    from_ost = DictAttrProperty('_info', 'from_ost', default=False)
    from_compilation = DictAttrProperty('_info', 'compilation', default=False)
    __collaborators = DictAttrProperty('_info', 'collaborators', default_factory=list)
    _artist = DictAttrProperty('_info', 'artist', default=None)
    _from_disco_info = DictAttrProperty('_info', 'from_discography_info', default=False)

    def __init__(self, info, collection, artist_context):
        super().__init__()
        self._info = info   # num, length, language, version, name_parts, collaborators, misc, artist
        self._artist_context = artist_context
        self.collection = collection
        # log.debug('Initializing track from={!r} with name={!r}'.format(collection, self._info['name_parts']))
        try:
            self.english_name, self.cjk_name = self._info['name_parts']
        except ValueError:
            if len(self._info['name_parts']) == 1:
                name = self._info['name_parts'][0]
                lang = LangCat.categorize(name)
                if lang in (LangCat.MIX, LangCat.ENG):
                    self.english_name = name
                    self.cjk_name = ''
                else:
                    self.english_name = ''
                    self.cjk_name = name
            else:
                raise
        self.name = multi_lang_name(self.english_name, self.cjk_name)
        # fmt = 'WikiTrack: artist_context={}, collection={}, name={}, collabs={}'
        # log.debug(fmt.format(artist_context, collection, self.name, self._info.get('collaborators')))
        self.__processed_collabs = False

    def __process_collabs(self):
        if self.__processed_collabs:
            return
        self.__processed_collabs = True
        if self.from_ost and self._artist_context:
            # log.debug('Processing collabs from OST {!r} w/ artist_context={!r}'.format(self.name, self._artist_context), extra={'color': (1, 230)})
            # log.debug('Comparing collabs={} to aliases={}'.format(self._collaborators, self._artist_context.aliases))
            if not self._from_disco_info:
                if not any(self._artist_context.matches(c['artist']) for c in self._collaborators.values()):
                    # fmt = 'WikiTrack {!r} discarding artist context={}; collabs: {}'
                    # log.debug(fmt.format(self.name, self._artist_context, self._collaborators), extra={'color': 'cyan'})
                    self._artist_context = None
                else:
                    for lc_collab, collab in sorted(self._collaborators.items()):
                        if self._artist_context.matches(collab['artist']):
                            self._collaborators.pop(lc_collab)
        else:
            # Clean up the collaborator list for tracks that include the primary artist in the list of collaborators
            # Example case: LOONA pre-debut single albums
            if self._collaborators:
                # log.debug('Processing collabs from {!r}: {!r}'.format(self.name, self._collaborators), extra={'color': (1, 230)})
                if self._artist and self._artist.lower() in self._collaborators:
                    # fmt = 'WikiTrack {!r} discarding artist from collaborators: artist={!r}; collabs: {}'
                    # log.debug(fmt.format(self.name, self._artist, self._collaborators), extra={'color': 'cyan'})
                    self._collaborators.pop(self._artist.lower())
                elif self.collection:
                    try:
                        artist = self.collection.artist
                    except NoPrimaryArtistError as e:
                        log.log(7, 'No single artist found for track={} from {}'.format(self, self.collection))
                    except Exception as e:
                        fmt = 'Error processing artist for track {!r} from {}: {}'
                        log.debug(fmt.format(self.name, self.collection, e))
                        # traceback.print_exc()
                    else:
                        # fmt = 'WikiTrack {!r} discarding album artist from collaborators: artist={!r}; collabs: {}'
                        # log.debug(fmt.format(self.name, artist, self._collaborators), extra={'color': 'cyan'})
                        for lc_collab, collab in sorted(self._collaborators.items()):
                            if artist.matches(collab['artist']):
                                self._collaborators.pop(lc_collab)

    @cached_property
    def _repr(self):
        if self.num is not None:
            name = '{}[{:2d}][{!r}]'.format(type(self).__name__, self.num, self.name)
        else:
            name = '{}[??][{!r}]'.format(type(self).__name__, self.name)
        len_str = '[{}]'.format(self.length_str) if self.length_str != '-1:00' else ""
        return '<{}{}>'.format(name, len_str)

    def __repr__(self):
        if self.num is not None:
            name = '{}[{:2d}][{!r}]'.format(type(self).__name__, self.num, self.name)
        else:
            name = '{}[??][{!r}]'.format(type(self).__name__, self.name)
        len_str = '[{}]'.format(self.length_str) if self.length_str != '-1:00' else ""
        return '<{}{}{}>'.format(name, "".join(self._formatted_name_parts()), len_str)

    @cached_property
    def _collaborators(self):
        collabs = {}
        addl_collabs = []
        for collab in chain(self.__collaborators, addl_collabs):
            if collab:
                # log.debug('WikiTrack[{!r}]: processing collaborator: {}'.format(self.name, collab))
                if isinstance(collab, dict):
                    try:
                        eng, cjk = collab['artist']
                    except ValueError as e:
                        if isinstance(collab['artist'], str):
                            name = collab['artist']
                        else:
                            err_fmt = 'Unexpected collaborator artist for track {} from collection {}: {}'
                            log.error(err_fmt.format(self.name, self.collection, collab['artist']))
                            raise e
                    else:
                        name = eng or cjk
                    collabs[name.lower()] = collab
                elif isinstance(collab, list):
                    addl_collabs.extend(collab)
                else:
                    collabs[collab.lower()] = {'artist': collab}
        return collabs

    @cached_property
    def artists(self):
        self.__process_collabs()
        collabs = []
        for collab in self._collaborators.values():
            artist = self.collection._get_artist(collab)
            if artist is not None:
                collabs.append(artist)
        return collabs

    @cached_property
    def collaborators(self):
        self.__process_collabs()
        collabs = []
        for collab in self._collaborators.values():
            try:
                artist = self.collection._get_artist(collab)
                # artist = WikiArtist(
                #     collab.get('artist_href'), aliases=collab['artist'], of_group=collab.get('of_group')
                # )
            except Exception as e:
                artist = collab['artist']
                if not isinstance(artist, str):
                    eng, cjk = artist
                    if eng and cjk:
                        artist = '{} ({})'.format(eng, cjk)
                    else:
                        artist = eng or cjk
                of_group = collab.get('of_group')
                if of_group:
                    artist = '{} [{}]'.format(artist, of_group)
            else:
                if artist:
                    artist = artist.qualname if collab.get('of_group') else artist.name
                else:
                    artist = collab['artist']
                    if not isinstance(artist, str):
                        eng, cjk = artist
                        if eng and cjk:
                            artist = '{} ({})'.format(eng, cjk)
                        else:
                            artist = eng or cjk
                    of_group = collab.get('of_group')
                    if of_group:
                        artist = '{} [{}]'.format(artist, of_group)

            collabs.append(artist)
        return collabs

    @cached_property
    def artist(self):
        if self._artist_context:
            return self._artist_context
        else:
            try:
                return self.collection.artist
            except NoPrimaryArtistError as e:
                if self.collection._category == 'soundtrack' and len(self.artists) == 1:
                    return self.artists[0]
                raise e

    @property
    def _cmp_attrs(self):
        return self.collection, self.disk, self.num, self.long_name

    def __lt__(self, other):
        comparison_type_check(self, other, WikiTrack, '<')
        return self._cmp_attrs < other._cmp_attrs

    def __gt__(self, other):
        comparison_type_check(self, other, WikiTrack, '>')
        return self._cmp_attrs > other._cmp_attrs

    @cached_property
    def is_inst(self):
        if self.version and self.version.lower().startswith('inst'):
            return True
        if self.misc:
            try:
                return any(m.lower().startswith('inst') for m in self.misc)
            except Exception as e:
                pass
        return False

    @cached_property
    def _edition_specific(self):
        if self.version and 'only' in self.version.lower():
            return True
        return self.misc and any('only' in m.lower() for m in self.misc)

    def _formatted_name_parts(self, incl_collabs=True, incl_solo=True):
        self.__process_collabs()
        parts = []
        if self.version:
            parts.append('{} ver.'.format(self.version) if not self.version.lower().startswith('inst') else self.version)
        if self.language:
            parts.append('{} ver.'.format(self.language))
        if self.misc:
            parts.extend(self.misc)
        if incl_solo and self._artist:
            artist_aliases = set(chain.from_iterable(artist.aliases for artist in self.collection.artists))
            if self._artist not in artist_aliases:
                parts.append('{} solo'.format(self._artist))
        if incl_collabs and self._collaborators:
            collabs = ', '.join(self.collaborators)
            if self.from_compilation or (self.from_ost and self._artist_context is None):
                parts.insert(0, 'by {}'.format(collabs))
            else:
                parts.append('Feat. {}'.format(collabs))
        return tuple(map('({})'.format, parts))

    def custom_name(self, *args, **kwargs):
        return ' '.join(chain((self.name,), self._formatted_name_parts(*args, **kwargs)))

    @cached_property
    def long_name(self):
        return ' '.join(chain((self.name,), self._formatted_name_parts()))

    def _additional_aliases(self):
        name_end = ' '.join(self._formatted_name_parts())
        aliases = [self.long_name]
        for val in self.english_name, self.cjk_name:
            if val:
                aliases.append('{} {}'.format(val, name_end).strip())
        return aliases

    @property
    def seconds(self):
        m, s = map(int, self.length_str.split(':'))
        return (s + (m * 60)) if m > -1 else 0

    def expected_filename(self, ext='mp3', incl_collabs=True, incl_solo=True):
        base = sanitize_path('{}.{}'.format(self.custom_name(incl_collabs, incl_solo), ext))
        if self.collection.has_multiple_disks:
            num_prefix = '{}-{:02d}. '.format(self.disk, self.num) if self.num else ''
        else:
            num_prefix = '{:02d}. '.format(self.num) if self.num else ''
        return num_prefix + base

    def expected_rel_path(self, ext='mp3', incl_collabs=True, incl_solo=True, **kwargs):
        album_rel_path = self.collection.expected_rel_path(**kwargs)
        return album_rel_path.joinpath(self.expected_filename(ext, incl_collabs, incl_solo))

    @classmethod
    def _normalize_for_matching(cls, other):
        if isinstance(other, str):
            m = cls.__feat_rx.search(other)
            if m:
                feat = m.group(1)
                if ' of ' in feat:
                    full_feat = feat
                    feat, of_group = feat.split(' of ', 1)
                else:
                    full_feat = None

                if LangCat.contains_any(feat, LangCat.asian_cats):
                    other_str = other
                    if full_feat:
                        other = {other_str.replace(feat, val) for val in romanized_permutations(feat)}
                        # The replacement of the full text below is intentional
                        other.update(other_str.replace(full_feat, val) for val in romanized_permutations(feat))
                    else:
                        other = {other_str.replace(feat, val) for val in romanized_permutations(feat)}

                    other.add(other_str)
                    other = tuple(sorted(other))
            else:
                lc_other = other.lower()
                if 'japanese ver.' in lc_other and LangCat.contains_any(other, LangCat.JPN):
                    try:
                        parsed = ParentheticalParser().parse(other)
                    except Exception:
                        pass
                    else:
                        for i, part in enumerate(parsed):
                            if part.lower().startswith('japanese ver'):
                                parsed.pop(i)
                                break
                        other = (other, ' '.join(parsed))
                else:
                    orig = other
                    inst = False
                    if lc_other.endswith('(inst.)'):
                        inst = True
                        other = other[:-7].strip()

                    if not LangCat.contains_any(other, LangCat.ENG) and LangCat.categorize(other) == LangCat.MIX:
                        try:
                            parsed = ParentheticalParser().parse(other)
                        except Exception:
                            other = orig
                        else:
                            other = tuple(['{}{}'.format(p, ' (Inst.)' if inst else '') for p in parsed] + [orig])
        return other

    def score_match(self, other, *args, normalize=True, **kwargs):
        if normalize:
            other = self._normalize_for_matching(other)
        return super().score_match(other, *args, **kwargs)


def find_ost(artist, title, disco_entry):
    empty_filters = WikiSoundtrack._search_filters is not None
    if WikiSoundtrack._search_filters or empty_filters:
        _title = WikiSoundtrack._pre_match_prep(title)
        if (not any(WikiSoundtrack.score_simple(_title, f) for f in WikiSoundtrack._search_filters)) or empty_filters:
            log.debug('Skipping full lookup for {} due to OST filter'.format(disco_entry))
            client = WikiClient.for_site(disco_entry.get('wiki')) if disco_entry.get('wiki') else None
            return WikiSoundtrack(
                disco_entry.get('uri_path'), client, disco_entry=disco_entry, artist_context=artist, no_fetch=True
            )

    try:
        norm_title_rx = find_ost._norm_title_rx
    except AttributeError:
        norm_title_rx = find_ost._norm_title_rx = re.compile(r'^(.*)\s+(?:Part|Code No)\.?\s*\d+$', re.IGNORECASE)

    # log.debug('find_ost({}, {!r}, {})'.format(artist, title, disco_entry), extra={'color': 10})

    orig_title = title
    m = norm_title_rx.match(title)
    if m:
        title = m.group(1).strip()
        if title.endswith(' -'):
            title = title[:-1].strip()
        log.log(2, 'find_ost: normalized {!r} -> {!r}'.format(orig_title, title))

    d_client = DramaWikiClient()
    if artist is not None and not isinstance(artist._client, DramaWikiClient):
        try:
            d_artist = artist.for_alt_site(d_client)
        except (WikiTypeError, WikiEntityInitException) as e:
            pass
        except Exception as e:
            log.debug('Error finding {} version of {}: {}\n{}'.format(d_client._site, artist, e, traceback.format_exc()), extra={'color': 14})
        else:
            # log.debug('Found {} version of artist: {} - {}'.format(d_client, d_artist, d_artist.url), extra={'color': 14})
            ost_match = d_artist.find_song_collection(title)
            if ost_match:
                log.debug('{}: Found OST fuzzy match {!r}={} via artist'.format(artist, title, ost_match), extra={'color': 10})
                return ost_match

    if title.endswith(' OST'):
        show_title = ' '.join(title.split()[:-1])
    elif LangCat.categorize(title) == LangCat.MIX and 'OST' in title.upper():
        show_title = re.sub(r'\sOST(?!$|[!a-zA-Z])', ' ', title, flags=re.IGNORECASE)
        show_title = ' '.join(show_title.split())
    else:
        show_title = title

    # log.debug('{}: Searching for show {!r} for OST {!r}'.format(artist, show_title, title))
    search_title = show_title
    if 'love' in show_title.lower():
        search_title = '|'.join([show_title, re.sub('love', 'luv', show_title, flags=re.IGNORECASE)])
    elif 'luv' in show_title.lower():
        search_title = '|'.join([show_title, re.sub('luv', 'love', show_title, flags=re.IGNORECASE)])

    w_client = WikipediaClient()
    for client in (d_client, w_client):
        search_results = client.search(search_title)
        log.debug('Found {} search results for title={!r} from {}'.format(len(search_results), search_title, client._site), extra={'color':'yellow'})
        for link_text, link_uri_path in search_results[:6]:
            try:
                series = WikiTVSeries(link_uri_path, client)
            except AmbiguousEntityException:
                continue
            except WikiTypeError:
                if isinstance(client, DramaWikiClient):
                    try:
                        actor = WikiArtist(link_uri_path, client)
                    except WikiTypeError:
                        continue
                    else:
                        series = None
                        for _series in actor.tv_shows:
                            if _series.matches(show_title):
                                series = _series
                                break
                        if not series:
                            continue
                else:
                    continue

            log.debug('Found search result for {!r}: {} @ {}'.format(search_title, series, series.url))

            if not series.matches(show_title):
                log.debug('{} does not match {!r}'.format(series, show_title))
                continue
            elif series.ost_hrefs:
                for ost_href in series.ost_hrefs:
                    ost = WikiSongCollection(ost_href, d_client, disco_entry=disco_entry, artist_context=artist)
                    if len(series.ost_hrefs) == 1 or ost.matches(title):
                        return ost

            for alt_title in series.aka:
                # log.debug('Found AKA for {!r}: {!r}'.format(show_title, alt_title))
                alt_uri_path = d_client.normalize_name(alt_title + ' OST')
                if alt_uri_path:
                    log.debug('Found alternate uri_path for {!r}: {!r}'.format(title, alt_uri_path))
                    return WikiSongCollection(
                        alt_uri_path, d_client, disco_entry=disco_entry, artist_context=artist
                    )

    results = w_client.search(show_title)   # At this point, there was no exact match for this search
    log.debug('Found {} search results for show={!r}'.format(len(results), show_title), extra={'color':'yellow'})
    if results:
        # log.debug('Trying to match {!r} to {!r}'.format(show_title, results[0][1]))
        try:
            series = WikiTVSeries(results[0][1], w_client)
        except (WikiTypeError, AmbiguousEntityException):
            pass
        else:
            if series.matches(show_title):
                alt_uri_path = d_client.normalize_name(series.name + ' OST')
                if alt_uri_path:
                    log.debug('Found alternate uri_path for {!r}: {!r}'.format(title, alt_uri_path))
                    return WikiSongCollection(alt_uri_path, d_client, disco_entry=disco_entry, artist_context=artist)

    k_client = KpopWikiClient()
    if disco_entry.get('wiki') == k_client._site and disco_entry.get('uri_path'):
        return WikiSoundtrack(disco_entry['uri_path'], k_client, disco_entry=disco_entry, artist_context=artist)

    return None