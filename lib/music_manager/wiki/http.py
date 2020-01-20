"""
Library for retrieving data from `MediaWiki sites via REST API <https://www.mediawiki.org/wiki/API>`_ or normal
requests.

:author: Doug Skrypa
"""

import logging
from collections import defaultdict

from requests_client import RequestsClient

__all__ = ['MediaWikiClient']
log = logging.getLogger(__name__)


class MediaWikiClient(RequestsClient):
    def __init__(self, *args, **kwargs):
        headers = kwargs.get('headers') or {}
        headers.setdefault('Accept', 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8')
        headers.setdefault('Accept-Encoding', 'gzip, deflate')
        headers.setdefault('Accept-Language', 'en-US,en;q=0.5')
        headers.setdefault('Upgrade-Insecure-Requests', '1')
        super().__init__(*args, **kwargs)

    @classmethod
    def _update_params(cls, params):
        params['format'] = 'json'
        params['formatversion'] = 2
        for key, val in params.items():
            # TODO: Figure out U+001F usage when a value containing | is found
            # Docs: If | in value, use U+001F as the separator & prefix value with it, e.g. param=%1Fvalue1%1Fvalue2
            if isinstance(val, list):
                params[key] = '|'.join(map(str, val))
                # params[key] = ''.join(map('\u001f{}'.format, val))    # doesn't work for vals without |
        return params

    def query(self, **params):
        """
        Submit, then parse and transform a `query request <https://www.mediawiki.org/wiki/API:Query>`_

        If the response contained a ``continue`` field, then additional requests will be submitted to gather all of the
        results.

        Note: Limit of 50 titles per query, though API docs say the limit for bots is 500

        :param params: Query API parameters
        :return dict: Mapping of {title: dict(results)}
        """
        params['action'] = 'query'
        params['redirects'] = 1
        properties = params.get('prop', [])
        properties = {properties} if isinstance(properties, str) else set(properties)
        if 'iwlinks' in properties:
            params['iwurl'] = 1
        params = self._update_params(params)

        resp = self.get('api.php', params=params)
        parsed, more = self._parse_query(resp)
        while more:
            continue_params = params.copy()
            continue_params['prop'] = '|'.join(more.keys())
            for continue_cmd in more.values():
                continue_params.update(continue_cmd)

            resp = self.get('api.php', params=params)
            _parsed, more = self._parse_query(resp)
            for title, data in _parsed.items():
                full = parsed[title]
                for key, val in data.items():
                    full_val = full[key]
                    if key == 'iwlinks':
                        for iw_name, iw_links in val.items():
                            full_val[iw_name].update(iw_links)
                    else:
                        if isinstance(full_val, list):
                            full_val.extend(val)
                        elif isinstance(full_val, dict):
                            full_val.update(val)
                        else:
                            msg = f'Unexpected value to merge for title={title!r} key={key!r} '     # space intentional
                            msg += f'type={type(full_val).__name__} full_val={full_val!r} new val={val!r}'
                            log.error(msg)




        return parsed

    @classmethod
    def _parse_query(cls, resp):
        response = resp.json()
        parsed = {}
        for page_id, page in response['query']['pages'].items():
            title = page['title']
            content = parsed[title] = {}
            for key, val in page.items():
                if key == 'revisions':
                    content[key] = [rev['*'] for rev in val]
                elif key == 'categories':
                    content[key] = [cat['title'].split(':', maxsplit=1)[1] for cat in val]
                elif key == 'iwlinks':
                    iwlinks = content[key] = defaultdict(dict)  # Mapping of {wiki name: {title: full url}}
                    for iwlink in val:
                        iwlinks[iwlink['prefix']][iwlink['*']] = iwlink['url']
                elif key == 'links':
                    content[key] = [link['title'] for link in val]
                else:
                    content[key] = val
        more = response.get('query-continue')
        return parsed, more

    def parse(self, **params):
        """
        Submit, then parse and transform a `parse request <https://www.mediawiki.org/wiki/API:Parse>`_

        The parse API only accepts one page at a time.

        :param params: Parse API parameters
        :return:
        """
        params['action'] = 'parse'
        params['redirects'] = 1
        properties = params.get('prop', [])
        properties = {properties} if isinstance(properties, str) else set(properties)
        if 'text' in properties:
            params['disabletoc'] = 1
            params['disableeditsection'] = 1

        resp = self.get('api.php', params=self._update_params(params))
        content = {}
        page = resp.json()['parse']
        for key, val in page.items():
            if key in ('wikitext', 'categorieshtml'):
                content[key] = val['*']
            elif key == 'text':
                content['html'] = val['*']
            elif key == 'categories':
                content[key] = [cat['*'] for cat in val]
            elif key == 'iwlinks':
                iwlinks = content[key] = defaultdict(dict)  # Mapping of {wiki name: {title: full url}}
                for iwlink in val:
                    link_text = iwlink['*'].split(':', maxsplit=1)[1]
                    iwlinks[iwlink['prefix']][link_text] = iwlink['url']
            elif key == 'links':
                content[key] = [wl['*'] for wl in val]
            else:
                content[key] = val
        return content

    def query_content(self, titles):
        """Get the contents of the latest revision of one or more pages as wikitext."""
        resp = self.query(titles=titles, rvprop='content', prop='revisions', rvslots='*')
        processed = {}
        for title, data in resp.items():
            revisions = data.get('revisions')
            processed[title] = revisions[0] if revisions else None
        return processed

    def query_categories(self, titles):
        """Get the categories of one or more pages."""
        resp = self.query(titles=titles, prop='categories')
        return {title: data.get('categories', []) for title, data in resp.items()}

    def query_pages(self, titles):
        """
        Get the full page content and the following additional data about each of the provided page titles:\n
          - categories

        :param str|list titles: One or more page titles (as it appears in the URL for the page)
        :return dict: Mapping of {title: dict(page data)}
        """
        resp = self.query(titles=titles, rvprop='content', prop=['revisions', 'categories'], rvslots='*')
        processed = {}
        for title, data in resp.items():
            revisions = data.get('revisions')
            processed[title] = {
                'categories': data.get('categories', []),
                'wikitext': revisions[0] if revisions else None
            }
        return processed

    def parse_page(self, page):
        resp = self.parse(page=page, prop=['wikitext', 'text', 'categories', 'links', 'iwlinks', 'displaytitle'])
        return resp
