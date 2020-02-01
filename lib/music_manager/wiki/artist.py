"""
:author: Doug Skrypa
"""

import logging

from ds_tools.compat import cached_property
from ds_tools.wiki.http import MediaWikiClient
from ds_tools.wiki.nodes import Table, List, ListEntry, Link, String, MixedNode
from .base import PersonOrGroup
from .album import SongCollection

__all__ = ['Artist', 'Singer', 'Group']
log = logging.getLogger(__name__)


class Artist(PersonOrGroup):
    _categories = ()

    @cached_property
    def discography(self):
        # TODO: Build this from all pages, not just the first one that works.  Some sites have items that others missed
        for site, page in self._pages.items():
            try:
                section = page.sections.find('Discography')
            except (KeyError, AttributeError):
                continue
            else:
                return section
        return None


class Singer(Artist):
    _categories = ('singer', 'actor', 'actress')


class Group(Artist):
    _categories = ('group',)

    @cached_property
    def members(self):
        for site, page in self._pages.items():
            try:
                content = page.sections.find('Members').content
            except (KeyError, AttributeError):
                continue

            titles = []
            if isinstance(content, Table):
                for row in content:
                    name = row.get('Name', row.get('name'))
                    if name:
                        if isinstance(name, Link):
                            titles.append(name.title)
                        elif isinstance(name, String):
                            titles.append(name.value)
                        else:
                            log.warning(f'Unexpected name type: {name!r}')

            if titles:
                client = MediaWikiClient(site)
                pages = client.get_pages(titles)
                return [Singer.from_page(member) for member in pages.values()]
        return []
