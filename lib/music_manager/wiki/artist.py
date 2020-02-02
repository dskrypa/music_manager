"""
:author: Doug Skrypa
"""

import logging
from datetime import datetime

from ds_tools.compat import cached_property
from ds_tools.wiki.http import MediaWikiClient
from ds_tools.wiki.nodes import Table, List, ListEntry, Link, String, MixedNode, CompoundNode
from .album import DiscographyEntry
from .base import PersonOrGroup
from .discography import DiscographyEntryFinder
from .shared import DiscoEntry

__all__ = ['Artist', 'Singer', 'Group']
log = logging.getLogger(__name__)


class Artist(PersonOrGroup):
    _categories = ()

    @cached_property
    def discography_entries(self):
        finder = DiscographyEntryFinder()

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
                            links = list(entry.find_all(Link, True))
                            if links:
                                for link in links:
                                    finder.add_entry_link(client, link, disco_entry)
                            else:
                                if isinstance(entry[1], String):
                                    disco_entry.title = entry[1].value
                                finder.add_entry(disco_entry, entry)
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
                                    links = list(entry.find_all(Link, True))
                                    if links:
                                        for link in links:
                                            finder.add_entry_link(client, link, disco_entry)
                                    else:
                                        if isinstance(entry[0], String):
                                            disco_entry.title = entry[0].value
                                        finder.add_entry(disco_entry, entry)
                    else:
                        log.warning(f'Unexpected section depth: {section.depth}')

        return finder.process_entries()


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
