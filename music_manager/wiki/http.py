"""
Library for retrieving data from `MediaWiki sites via REST API <https://www.mediawiki.org/wiki/API>`_ or normal
requests.

:author: Doug Skrypa
"""

import logging

from requests_client import RequestsClient

__all__ = ['WikiClient']
log = logging.getLogger(__name__)


class WikiClient(RequestsClient):
    def _query(self, **params):
        """
        Note: Limit of 50 titles per query, though API docs say the limit for bots is 500

        :param params:
        :return:
        """
        params['action'] = 'query'
        params['format'] = 'json'
        for key, val in params.items():
            if isinstance(val, list):
                params[key] = '|'.join(map(str, val))
        resp = self.get('api.php', params=params)
        parsed = {}
        for page_id, page in resp.json()['query']['pages'].items():
            title = page['title']
            content = parsed[title] = {}
            for key, val in page.items():
                if key == 'revisions':
                    content[key] = [rev['*'] for rev in val]
                elif key == 'categories':
                    content[key] = [cat['title'].split(':', maxsplit=1)[1] for cat in val]
                else:
                    content[key] = val
        return parsed

    def query_content(self, titles):
        """Get the contents of the latest revision of one or more pages as wikitext."""
        resp = self._query(titles=titles, rvprop='content', prop='revisions', rvslots='*')
        return {title: data['revisions'][0] for title, data in resp.items()}

    def query_categories(self, titles):
        """Get the categories of one or more pages."""
        resp = self._query(titles=titles, prop='categories')
        return {title: data['categories'] for title, data in resp.items()}

    def query_pages(self, titles):
        """
        Get the full page content and the following additional data about each of the provided page titles:\n
          - categories

        :param str|list titles: One or more page titles (as it appears in the URL for the page)
        :return dict: Mapping of {title: dict(page data)}
        """
        resp = self._query(titles=titles, rvprop='content', prop=['revisions', 'categories'], rvslots='*')
        processed = {}
        for title, data in resp.items():
            processed[title] = {'content': data['revisions'][0], 'categories': data['categories']}
        return processed
