"""
:author: Doug Skrypa
"""

import logging
import re
import string
from urllib.parse import urlparse

import bs4

from db_cache import DBCache
from ds_tools.caching import cached
from ds_tools.http import CodeBasedRestException
from ds_tools.utils import ParentheticalParser
from ds_tools.utils.soup import soupify
from requests_client import RequestsClient
from .exceptions import *
from .parsing import parse_aside, parse_infobox, parse_album_page, parse_wikipedia_album_page
from .utils import get_page_category

__all__ = ['DramaWikiClient', 'KindieWikiClient', 'KpopWikiClient', 'WikiClient', 'WikipediaClient']
log = logging.getLogger(__name__)
logr = {'normalize': logging.getLogger(__name__ + '.normalize')}
for logger in logr.values():
    logger.setLevel(logging.WARNING)

AMBIGUOUS_URI_PATH_TEXT = [
    'This article is a disambiguation page', 'Wikipedia does not have an article with this exact name.',
    'This disambiguation page lists articles associated with',
    'The deletion and move log for the page are provided below for reference.'
]
JUNK_CHARS = string.whitespace + string.punctuation
STRIP_TBL = str.maketrans({c: '' for c in JUNK_CHARS})


def http_req_cache_key(self, endpoint, *args, **kwargs):
    params = kwargs.get('params')
    url = self.url_for(endpoint)
    if params:
        return url, tuple(sorted(params.items()))
    return url


class WikiClient(RequestsClient):
    _site = None
    _sites = {}
    __instances = {}

    def __init_subclass__(cls, **kwargs):  # Python 3.6+
        if cls._site:
            WikiClient._sites[cls._site] = cls

    def __new__(cls, *args, **kwargs):
        if cls.__instances.get(cls) is None:
            cls.__instances[cls] = super().__new__(cls)
        return cls.__instances[cls]

    def __init__(self, host=None, prefix='wiki', proto='https', **kwargs):
        if not getattr(self, '_WikiClient__initialized', False):
            super().__init__(
                host or self._site, rate_limit=0.5, path_prefix=prefix, scheme=proto, log_params=True,
                exc=CodeBasedRestException, **kwargs
            )
            self._resp_cache = DBCache('responses', cache_subdir='kpop_wiki')
            self._name_cache = DBCache('names', cache_subdir='kpop_wiki')
            self._bad_name_cache = DBCache('invalid_names', cache_subdir='kpop_wiki')
            self.__initialized = True

    def get_url_for(self, endpoint, allow_alt_sites=False):
        if allow_alt_sites and endpoint.startswith(('http://', 'https://', '//')):
            _url = urlparse(endpoint)
            uri_path = _url.path[6:] if _url.path.startswith('/wiki/') else _url.path
            return self.for_site(_url.hostname).url_for(uri_path)
        return super().url_for(endpoint)

    @classmethod
    def for_site(cls, site):
        if site.startswith(('http', '//')):
            site = urlparse(site).hostname
        try:
            return cls._sites[site]()
        except KeyError as e:
            raise ValueError('No WikiClient class exists for site {!r}'.format(site)) from e

    # @cached('_resp_cache', lock=True, key=lambda s, e, *a, **kw: s.url_for(e), exc=True, optional=True)
    @cached('_resp_cache', lock=True, key=http_req_cache_key, exc=True, optional=True)
    def get(self, *args, **kwargs):
        return super().get(*args, **kwargs)

    @cached(True, exc=True)  # Prevent needing to repeatedly unpickle
    def get_page(self, endpoint, **kwargs):
        url = self.url_for(endpoint)
        log.log(7, 'GET -> {}'.format(url))
        # if '/Part_' in url:
        #     raise BaseException('Invalid path requires investigation: {}'.format(url))
        return self.get(endpoint, **kwargs).text

    @cached('_name_cache', lock=True, key=lambda s, a: '{}: {}'.format(s.host, a), optional=True)
    def normalize_name(self, name):
        name = name.strip()
        if not name:
            raise ValueError('A valid name must be provided')
        _log = logr['normalize']
        _name = name
        name = name.replace(' ', '_')
        try:
            html = self.get_page(name)
        except CodeBasedRestException as e:
            _log.debug('{}: Error getting page {!r}: code={!r}, {}'.format(self._site, name, e.code, e))
            if e.code == 404:
                self._bad_name_cache[name] = True
                aae = AmbiguousEntityException(e.resp.url, e.resp.text)
                return self.__normalize_ambiguous_name(name, _name, aae, e)
            raise e
        else:
            if any(val in html for val in AMBIGUOUS_URI_PATH_TEXT):
                _log.debug('{}: Page {!r} exists, but is a disambiguation page'.format(self._site, name))
                aae = AmbiguousEntityException(self.url_for(name), html)
                return self.__normalize_ambiguous_name(name, _name, aae)
            _log.debug('{}: Page {!r} exists, and appears to be valid'.format(self._site, name))
            return name

    def __normalize_ambiguous_name(self, name, orig_name, ambig_ent_exc, orig_exc=None):
        _log = logr['normalize']
        _log.debug('{}: Examining AmbiguousEntityException for {!r}: {}'.format(self._site, name, ambig_ent_exc))
        alt = ambig_ent_exc.alternative
        if alt:
            if alt.translate(STRIP_TBL).lower() == orig_name.translate(STRIP_TBL).lower():
                return alt
        else:
            try:
                parts = ParentheticalParser().parse(orig_name)
                name = parts[0]
            except Exception as pe:
                pass
            else:
                if name != orig_name:
                    _log.debug('{}: Checking {!r} for {!r}'.format(self._site, name, orig_name))
                    try:
                        return self._name_cache['{}: {}'.format(self.host, name)]
                    except KeyError as ke:
                        pass

        if orig_exc:
            raise ambig_ent_exc from orig_exc
        raise ambig_ent_exc

    normalize_artist = normalize_name

    def parse_side_info(self, soup, uri_path):
        return {}

    def parse_album_page(self, uri_path, clean_soup, side_info):
        return []

    def get_entity_base(self, uri_path, obj_type=None):
        raise NotImplementedError()

    def get_category(self, uri_path):
        if 'action=edit&redlink=1' in uri_path:
            return None
        if uri_path.startswith(('http', '//')):
            uri_path = urlparse(uri_path).path
        if uri_path.startswith((self.path_prefix, '/' + self.path_prefix)):
            uri_path = uri_path[len(self.path_prefix)+1:]
        raw, cats = self.get_entity_base(uri_path)
        return get_page_category(uri_path, cats, no_debug=True, raw=raw)

    def is_any_category(self, uri_path, categories=None):
        """
        :param str uri_path: A uri path relative to this client's root path
        :param None|container categories: A container holding one more more str categories to match against, or None to
          return True if the given uri_path's category is not None
        :return bool: True if the page with the given uri_path is one of the provided categories
        """
        if 'action=edit&redlink=1' in uri_path:
            return False
        if isinstance(categories, str):
            categories = (categories,)
        if uri_path.startswith(('http', '//')):
            uri_path = urlparse(uri_path).path
        if uri_path.startswith((self.path_prefix, '/' + self.path_prefix)):
            uri_path = uri_path[len(self.path_prefix)+1:]
        raw, cats = self.get_entity_base(uri_path)
        page_category = get_page_category(uri_path, cats, no_debug=True, raw=raw)
        return (page_category in categories) if categories is not None else (page_category is not None)


class KpopWikiClient(WikiClient):
    _site = 'kpop.fandom.com'

    @cached(True)
    def get_entity_base(self, uri_path, obj_type=None):
        raw = self.get_page(uri_path)
        # if 'This article is a disambiguation page' in raw:
        #     raise AmbiguousEntityException(uri_path, raw, obj_type)
        cat_ul = soupify(raw, parse_only=bs4.SoupStrainer('ul', class_='categories'))
        # cat_ul = soupify(raw).find('ul', class_='categories')
        return raw, {li.text.lower() for li in cat_ul.find_all('li')} if cat_ul else set()

    def parse_side_info(self, soup, uri_path):
        return parse_aside(soup, uri_path)

    def parse_album_page(self, uri_path, clean_soup, side_info):
        return parse_album_page(uri_path, clean_soup, side_info, self)

    def search(self, query):
        try:
            resp = self.get('Special:Search', params={'query': query})
        except CodeBasedRestException as e:
            log.debug('Error retrieving results for query {!r}: {}'.format(query, e))
            raise e

        results = []
        soup = soupify(resp.text, parse_only=bs4.SoupStrainer('ul', class_='Results'))
        for li in soup.find_all('li', class_='result'):
            a = li.find('a', class_='result-link')
            if a:
                href = a.get('href')
                if href:
                    url = urlparse(href)
                    uri_path = url.path
                    uri_path = uri_path[6:] if uri_path.startswith('/wiki/') else uri_path
                    results.append((a.text, uri_path))
        return results


class KindieWikiClient(KpopWikiClient):
    _site = 'kindie.fandom.com'


class WikipediaClient(WikiClient):
    _site = 'en.wikipedia.org'

    @cached(True)
    def get_entity_base(self, uri_path, obj_type=None):
        raw = self.get_page(uri_path)
        if any(val in raw for val in AMBIGUOUS_URI_PATH_TEXT):
            raise AmbiguousEntityException(self.url_for(uri_path), raw, obj_type)
        cat_links = soupify(raw, parse_only=bs4.SoupStrainer('div', id='mw-normal-catlinks'))
        cat_ul = cat_links.find('ul') if cat_links else None
        cats = {li.text.lower() for li in cat_ul.find_all('li')} if cat_ul else set()
        cat = get_page_category(uri_path, cats, no_debug=True, raw=raw)
        if cat in (None, 'misc'):
            if re.search(r'For other uses, see.*?\(disambiguation\)', raw, re.IGNORECASE):
                raise AmbiguousEntityException(self.url_for(uri_path), raw, obj_type)
            elif re.search(r'redirects here.\s+For the .*?, see', raw, re.IGNORECASE):
                raise AmbiguousEntityException(self.url_for(uri_path), raw, obj_type)
        return raw, cats

    def parse_side_info(self, soup, uri_path):
        return parse_infobox(soup, uri_path, self)

    def parse_album_page(self, uri_path, clean_soup, side_info):
        return parse_wikipedia_album_page(uri_path, clean_soup, side_info, self)

    def search(self, query):
        params = {'search': query, 'title': 'Special:Search', 'fulltext': 'Search'}
        try:
            resp = self.get('index.php', params=params)  #, use_cached=False)
        except CodeBasedRestException as e:
            log.debug('Error retrieving results for query {!r}: {}'.format(query, e))
            raise e

        results = []
        soup = soupify(resp.text, parse_only=bs4.SoupStrainer('ul', class_='mw-search-results'))
        for div in soup.find_all('div', class_='mw-search-result-heading'):
            a = div.find('a')
            if a:
                href = a.get('href')
                if href:
                    url = urlparse(href)
                    uri_path = url.path
                    uri_path = uri_path[6:] if uri_path.startswith('/wiki/') else uri_path
                    results.append((a.text, uri_path))
        return results


class DramaWikiClient(WikiClient):
    _site = 'wiki.d-addicts.com'

    def __init__(self):
        if not getattr(self, '_DramaWikiClient__initialized', False):
            super().__init__(prefix='')
            self.__initialized = True

    def get(self, *args, **kwargs):
        resp = super().get(*args, **kwargs)
        if 'There is currently no text in this page.' in resp.text:
            resp.status_code = 404
            raise CodeBasedRestException(resp, resp.url)
        return resp

    @cached(True)
    def get_entity_base(self, uri_path, obj_type=None):
        raw = self.get_page(uri_path)
        cat_links = soupify(raw, parse_only=bs4.SoupStrainer('div', id='mw-normal-catlinks'))
        # cat_links = soupify(raw).find('div', id='mw-normal-catlinks')
        cat_ul = cat_links.find('ul') if cat_links else None
        return raw, {li.text.lower() for li in cat_ul.find_all('li')} if cat_ul else set()

    def search(self, query):
        log.log(9, 'Searching {} for: {!r}'.format(self.host, query))
        try:
            resp = self.get('index.php', params={'search': query, 'title': 'Special:Search'})#, use_cached=False)
        except CodeBasedRestException as e:
            log.debug('Error retrieving results for query {!r}: {}'.format(query, e))
            raise e

        url = urlparse(resp.url)
        if url.path != '/index.php':    # If there's an exact match, it redirects to that page
            return [('', url.path[1:])]

        results = []
        soup = soupify(resp.text, parse_only=bs4.SoupStrainer('ul', class_='mw-search-results'))
        for div in soup.find_all('div', class_='mw-search-result-heading'):
            a = div.find('a')
            if a:
                href = a.get('href')
                if href:
                    results.append((a.text, urlparse(href).path))
        return results

    def title_search(self, title):
        try:
            resp = self.get('index.php', params={'search': title, 'title': 'Special:Search'})#, use_cached=False)
        except CodeBasedRestException as e:
            log.debug('Error searching for OST {!r}: {}'.format(title, e))
            raise e

        url = urlparse(resp.url)
        if url.path != '/index.php':    # If there's an exact match, it redirects to that page
            return url.path[1:]

        clean_title = title.translate(STRIP_TBL).lower()
        soup = soupify(resp.text, parse_only=bs4.SoupStrainer(class_='searchresults'))
        # for a in soup.find(class_='searchresults').find_all('a'):
        for a in soup.find_all('a'):
            clean_a = a.text.translate(STRIP_TBL).lower()
            if clean_a == clean_title or clean_title in clean_a:
                href = a.get('href') or ''
                if href and 'redlink=1' not in href:
                    return href

        lc_title = title.lower()
        keyword = next((val for val in ('the ', 'a ') if lc_title.startswith(val)), None)
        if keyword:
            return self.title_search(title[len(keyword):].strip())
        return None

    @cached('_name_cache', lock=True, key=lambda s, a: '{}: {}'.format(s.host, a))
    def normalize_name(self, name):
        return self.title_search(name)