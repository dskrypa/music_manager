"""
:author: Doug Skrypa
"""

import logging
from collections import defaultdict

from ds_tools.compat import cached_property
from ds_tools.wiki.http import MediaWikiClient
from ds_tools.wiki.nodes import Table, List, ListEntry, Link, String, MixedNode, CompoundNode
from .base import PersonOrGroup
from .album import DiscographyEntry

__all__ = ['Artist', 'Singer', 'Group']
log = logging.getLogger(__name__)


class Artist(PersonOrGroup):
    _categories = ()

    @cached_property
    def discography(self):
        # TODO: Build this from all pages, not just the first one that works.  Some sites have items that others missed
        for site, artist_page in self._pages.items():
            try:
                section = artist_page.sections.find('Discography')
            except (KeyError, AttributeError):
                continue

            if site == 'kpop.fandom.com':
                entries = {}
                if section.depth == 2:                                          # key = language, value = sub-section
                    for lang, lang_section in section.children.items():
                        for alb_type, alb_type_section in lang_section.children.items():
                            # log.debug(f'{at_section}: {at_section.content}')
                            content = alb_type_section.content
                            if type(content) is CompoundNode:   # A template for splitting the discography into columns
                                content = content[0]            # follows the list of albums in this section
                            for entry in content.iter_flat():
                                link = None
                                if isinstance(entry.value, Link):
                                    link = entry.value
                                elif type(entry.value) is CompoundNode:
                                    link = next(entry.value.find_all(Link), None)

                                if link:
                                    entries[link.title] = (entry.value, alb_type, lang)
                                else:
                                    log.warning(f'Unexpected entry content: {entry.value!r}')
                else:
                    log.warning(f'Unexpected section depth: {section.depth}')

                client = MediaWikiClient(site)
                current_site_links = []
                alt_site_links = defaultdict(dict)
                for link in entries:
                    if ':' in link:
                        iw_site, iw_title = map(str.strip, link.split(':', maxsplit=1))
                        iw_site = iw_site.lower()
                        if iw_site in client.interwiki_map:
                            iw_client = MediaWikiClient(client.interwiki_map[iw_site], nopath=True)
                            alt_site_links[iw_client][iw_title] = link
                        else:
                            current_site_links.append(link)
                    else:
                        current_site_links.append(link)

                pages = client.get_pages(current_site_links)
                discography = []
                for title, page in pages.items():
                    entry, alb_type, lang = entries[title]
                    discography.append(DiscographyEntry.from_page(
                        page, album_type=alb_type, language=lang, discography_entry=entry
                    ))
                for iw_client, iw_titles in alt_site_links.items():
                    pages = iw_client.get_pages(iw_titles.keys())
                    for title, page in pages.items():
                        link = iw_titles[title]
                        entry, alb_type, lang = entries[link]
                        discography.append(DiscographyEntry.from_page(
                            page, album_type=alb_type, language=lang, discography_entry=entry
                        ))

                return discography
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
