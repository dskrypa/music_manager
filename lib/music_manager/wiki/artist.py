"""
:author: Doug Skrypa
"""

import logging
from collections import defaultdict, Counter
from datetime import datetime

from ds_tools.compat import cached_property
from ds_tools.wiki.http import MediaWikiClient
from ds_tools.wiki.nodes import Table, List, ListEntry, Link, String, MixedNode, CompoundNode
from .album import DiscographyEntry
from .base import PersonOrGroup
from .exceptions import EntityTypeError
from .shared import DiscoEntry

__all__ = ['Artist', 'Singer', 'Group']
log = logging.getLogger(__name__)


class Artist(PersonOrGroup):
    _categories = ()

    @cached_property
    def discography_entries(self):
        found_page = defaultdict(lambda: False)
        remaining_links = Counter()
        entries_by_site = defaultdict(dict)

        # noinspection PyShadowingNames
        def _add_entry_link(client, link, disco_entry):
            remaining_links[disco_entry] += 1
            if link.interwiki:
                iw_key, iw_title = link.iw_key_title
                iw_client = client.interwiki_client(iw_key)
                entries_by_site[iw_client or client][iw_title if iw_client else link.title] = (disco_entry, link)
            else:
                entries_by_site[client][link.title] = (disco_entry, link)

        no_link_entries = []
        for site, artist_page in self._pages.items():
            client = MediaWikiClient(site)
            if site == 'www.generasia.com':
                for section_title in ('Discography', 'Korean Discography', 'Japanese Discography'):
                    try:
                        section = artist_page.sections.find(section_title)
                    except KeyError:
                        continue

                    lang = section_title.split()[0] if ' ' in section_title else None
                    for alb_type, alb_type_section in section.children.items():
                        if 'video' in alb_type.lower():
                            continue
                        content = alb_type_section.content
                        for entry in content.iter_flat():
                            date = datetime.strptime(entry[0].value, '[%Y.%m.%d]')
                            disco_entry = DiscoEntry(artist_page, entry, type_=alb_type, lang=lang, date=date)
                            links = list(disco_entry.node.find_all(Link, True))
                            if links:
                                for link in links:
                                    _add_entry_link(client, link, disco_entry)
                            else:
                                no_link_entries.append(disco_entry)
                                log.warning(f'Unexpected entry content: {entry!r}')
            else:
                try:
                    section = artist_page.sections.find('Discography')
                except KeyError:
                    continue

                if site == 'kpop.fandom.com':
                    if section.depth == 2:                                  # key = language, value = sub-section
                        for lang, lang_section in section.children.items():
                            for alb_type, alb_type_section in lang_section.children.items():
                                # log.debug(f'{at_section}: {at_section.content}')
                                content = alb_type_section.content
                                if type(content) is CompoundNode:   # A template for splitting the discography into
                                    content = content[0]            # columns follows the list of albums in this section
                                for entry in content.iter_flat():
                                    year = datetime.strptime(entry[-1].value.split()[-1], '(%Y)').year
                                    disco_entry = DiscoEntry(artist_page, entry, type_=alb_type, lang=lang, year=year)
                                    link = next(entry.find_all(Link, True), None)
                                    if link:
                                        _add_entry_link(client, link, disco_entry)
                                    else:
                                        no_link_entries.append(disco_entry)
                                        log.warning(f'Unexpected entry content: {entry!r}')
                    else:
                        log.warning(f'Unexpected section depth: {section.depth}')

        discography = []
        pages_by_site, errors_by_site = MediaWikiClient.get_multi_site_pages(entries_by_site)
        for site_client, title_entry_map in entries_by_site.items():
            for title, page in pages_by_site.get(site_client.host, {}).items():
                disco_entry, link = title_entry_map.pop(title)
                try:
                    discography.append(DiscographyEntry.from_page(page, disco_entry=disco_entry))
                except EntityTypeError as e:
                    remaining_links[disco_entry] -= 1
                    if found_page[disco_entry]:
                        log.log(9, f'Type mismatch for additional link={link} associated with {disco_entry}: {e}')
                    elif remaining_links[disco_entry]:
                        log.debug(f'{e}, but {remaining_links[disco_entry]} associated links are pending processing')
                    else:
                        log.warning(f'{e}, and no other links are available')

            for title, (disco_entry, link) in title_entry_map.items():
                log.debug(f'No page found for {link}')
                discography.append(DiscographyEntry(link.text or link.title, disco_entry=disco_entry))

        for disco_entry in no_link_entries:
            discography.append(DiscographyEntry(disco_entry=disco_entry))

        return discography


class Singer(Artist):
    _categories = ('singer', 'actor', 'actress', 'member')


class Group(Artist):
    _categories = ('group',)

    @cached_property
    def members(self):
        # TODO: Handle no links / incomplete links
        for site, page in self._pages.items():
            try:
                content = page.sections.find('Members').content
            except (KeyError, AttributeError):
                continue

            if type(content) is CompoundNode:
                for node in content:
                    if isinstance(node, (Table, List)):
                        content = node
                        break

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
            elif isinstance(content, List):
                for entry in content.iter_flat():
                    if isinstance(entry, Link):
                        titles.append(entry.title)
                    elif isinstance(entry, MixedNode) or type(entry) is CompoundNode:
                        link = next(entry.find_all(Link, True), None)
                        if link:
                            titles.append(link.title)
                    elif isinstance(entry, String):
                        titles.append(entry.value)
                    else:
                        log.warning(f'Unexpected name type: {entry!r}')

            if titles:
                client = MediaWikiClient(site)
                pages = client.get_pages(titles)
                return [Singer.from_page(member) for member in pages.values()]
        return []
