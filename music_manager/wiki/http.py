"""


:author: Doug Skrypa
"""

import logging

from requests_client import RequestsClient

__all__ = ['WikiClient']
log = logging.getLogger(__name__)


class WikiClient(RequestsClient):
    def _query(self, **params):
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
        return self._query(titles=titles, rvprop='content', prop='revisions', rvslots='*')

    def query_categories(self, titles):
        return self._query(titles=titles, prop='categories')

    def query_pages(self, titles):
        return self._query(titles=titles, rvprop='content', prop=['revisions', 'categories'], rvslots='*')
