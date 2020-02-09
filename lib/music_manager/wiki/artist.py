"""
:author: Doug Skrypa
"""

import logging
from datetime import datetime

from ds_tools.compat import cached_property
from ds_tools.wiki.http import MediaWikiClient
from ds_tools.wiki.nodes import Table, List, Link, String, MixedNode, CompoundNode, Template
from .album import DiscographyEntry
from .base import PersonOrGroup
from .discography import DiscographyEntryFinder, Discography
from .shared import DiscoEntry, DiscoEntryType

__all__ = ['Artist', 'Singer', 'Group']
log = logging.getLogger(__name__)


class Artist(PersonOrGroup):
    _categories = ()

    @cached_property
    def discography_entries(self):
        finder = DiscographyEntryFinder()
        collab_type = DiscoEntryType.Collaboration

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
                        de_type = DiscoEntryType.for_name(alb_type)
                        content = alb_type_section.content
                        for entry in content.iter_flat():
                            entry_type = de_type
                            entry_link = None
                            song_title = None
                            if de_type == collab_type and isinstance(entry, MixedNode) and len(entry) >= 5:
                                if isinstance(entry[2], String) and entry[2].value == '-' and isinstance(entry[3], Link):
                                    entry_type = DiscoEntryType.Feature
                                    entry_link = entry[3]
                                    if isinstance(entry[4], String) and not entry[4].value.lower().startswith('(feat'):
                                        song_title = entry[4].value[1:].partition('(')[0]
                                    else:
                                        song_title = entry_link.text or entry_link.title
                                # elif isinstance(entry[2], Link) and isinstance(entry[1], String) and entry[1].value.endswith(' -'):
                                #     entry_type = DiscoEntryType.Feature
                                #     entry_link = entry[2]
                                #     if isinstance(entry[3], String) and not entry[3].value.lower().startswith('(feat'):
                                #         song_title = entry[3].value[1:].partition('(')[0]
                                #     else:
                                #         song_title = entry_link.text or entry_link.title
                            if not entry_link:
                                entry_link = next(entry.find_all(Link, True), None)

                            date = datetime.strptime(entry[0].value, '[%Y.%m.%d]')
                            disco_entry = DiscoEntry(
                                artist_page, entry, type_=entry_type, lang=lang, date=date, link=entry_link,
                                song=song_title
                            )
                            if entry_link:
                                finder.add_entry_link(client, entry_link, disco_entry)
                            else:
                                if isinstance(entry[1], String):
                                    disco_entry.title = entry[1].value
                                finder.add_entry(disco_entry, entry)
            elif site == 'wiki.d-addicts.com':
                try:
                    section = artist_page.sections.find('TV Show Theme Songs')
                except KeyError:
                    continue
                # Typical format: {song title} [by {member}] - {soundtrack title} ({year})
                for entry in section.content.iter_flat():
                    year = datetime.strptime(entry[-1].value.split()[-1], '(%Y)').year
                    disco_entry = DiscoEntry(artist_page, entry, type_='Soundtrack', year=year)
                    links = list(entry.find_all(Link, True))
                    if not finder.add_entry_links(client, links, disco_entry):
                        if isinstance(entry[-2], String):
                            disco_entry.title = entry[-2].value
                        finder.add_entry(disco_entry, entry)
            elif site == 'kpop.fandom.com':
                try:
                    section = artist_page.sections.find('Discography')
                except KeyError:
                    continue

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
            elif site == 'en.wikipedia.org':
                try:
                    section = artist_page.sections.find('Discography')
                except KeyError:
                    log.debug(f'No discography section found for {artist_page}')
                    continue
                try:
                    disco_page_link_tmpl = section.content[0]
                except Exception as e:
                    log.debug(f'Unexpected error finding the discography page link on {artist_page}: {e}')
                    continue

                if isinstance(disco_page_link_tmpl, Template) and disco_page_link_tmpl.name.lower() == 'main':
                    try:
                        disco_page_title = disco_page_link_tmpl.value[0].value
                    except Exception as e:
                        log.debug(f'Unexpected error finding the discography page link on {artist_page}: {e}')
                    else:
                        disco_entity = Discography.from_page(client.get_page(disco_page_title))
                        disco_entity._process_entries(finder)
                else:
                    log.debug(f'Unexpected discography section format on {artist_page}')
            else:
                log.debug(f'No discography entry extraction is configured for {artist_page}')

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
