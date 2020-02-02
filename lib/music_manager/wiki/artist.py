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
from .shared import DiscoEntry

__all__ = ['Artist', 'Singer', 'Group']
log = logging.getLogger(__name__)


class Artist(PersonOrGroup):
    _categories = ()

    @cached_property
    def discography(self):
        entries_by_site = defaultdict(dict)
        no_link_entries = []
        for site, artist_page in self._pages.items():
            try:
                section = artist_page.sections.find('Discography')
            except KeyError:
                continue

            client = MediaWikiClient(site)
            entries = {}
            if site == 'kpop.fandom.com':
                if section.depth == 2:                                          # key = language, value = sub-section
                    for lang, lang_section in section.children.items():
                        for alb_type, alb_type_section in lang_section.children.items():
                            # log.debug(f'{at_section}: {at_section.content}')
                            content = alb_type_section.content
                            if type(content) is CompoundNode:   # A template for splitting the discography into columns
                                content = content[0]            # follows the list of albums in this section
                            for entry in content.iter_flat():
                                disco_entry = DiscoEntry(artist_page, entry.value, type_=alb_type, lang=lang)
                                if isinstance(entry.value, Link):
                                    entries[entry.value] = disco_entry
                                elif type(entry.value) is CompoundNode:
                                    link = next(entry.value.find_all(Link), None)
                                    if link:
                                        entries[link] = disco_entry
                                else:
                                    no_link_entries.append(disco_entry)
                                    log.warning(f'Unexpected entry content: {entry.value!r}')
                else:
                    log.warning(f'Unexpected section depth: {section.depth}')

            # Regardless of site being processed, sort entries by site
            for link, disco_entry in entries.items():
                if link.interwiki:
                    iw_key, iw_title = link.iw_key_title
                    iw_client = client.interwiki_client(iw_key)
                    entries_by_site[iw_client or client][iw_title if iw_client else link.title] = (disco_entry, link)
                else:
                    entries_by_site[client][link.title] = (disco_entry, link)

        discography = []
        for site_client, title_entry_map in entries_by_site.items():
            pages = site_client.get_pages(title_entry_map.keys())
            for title, page in pages.items():
                disco_entry = title_entry_map.pop(title)[0]
                discography.append(DiscographyEntry.from_page(page, disco_entry=disco_entry))

            for title, (disco_entry, link) in title_entry_map.items():
                log.debug(f'No page found for {link}')
                discography.append(DiscographyEntry(link.text or link.title, disco_entry=disco_entry))

        for disco_entry in no_link_entries:
            discography.append(DiscographyEntry(disco_entry=disco_entry))

        # TODO: Combine entries from multiple sites that refer to the same album
        return discography


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
