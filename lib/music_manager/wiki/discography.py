"""
:author: Doug Skrypa
"""

import logging
from collections import defaultdict, Counter

from ds_tools.compat import cached_property
from ds_tools.wiki.http import MediaWikiClient
from ds_tools.wiki.nodes import Table, List, ListEntry, Link, String, MixedNode, CompoundNode, TableSeparator
from .album import DiscographyEntry
from .base import WikiEntity
from .exceptions import EntityTypeError
from .shared import DiscoEntry

__all__ = ['Discography', 'DiscographyEntryFinder']
log = logging.getLogger(__name__)


class Discography(WikiEntity):
    _categories = ('discography', 'discographies')

    @cached_property
    def discography_entries(self):
        finder = DiscographyEntryFinder()
        for site, disco_page in self._pages.items():
            client = MediaWikiClient(site)
            if site == 'en.wikipedia.org':
                sections = []
                for section in disco_page.sections:
                    if section.title.lower() in ('footnotes', 'references'):
                        break
                    elif section.depth == 1:
                        sections.extend(section)
                    else:
                        sections.append(section)

                for section in sections:
                    alb_type = section.title
                    lang = None
                    for row in section.content:
                        # log.debug(f'Processing alb_type={alb_type} row={row}')
                        if isinstance(row, TableSeparator):
                            try:
                                lang = row.value.value
                            except AttributeError:      # Usually caused by a footnote about the table
                                pass
                        else:
                            title = row['Title']
                            details = row['Details'].as_dict() if 'Details' in row else None
                            if details:
                                date = details.get('Released', details.get('To be released'))
                                if date is not None:
                                    date = date.value
                                    if '(' in date:
                                        date = date.split('(', maxsplit=1)[0].strip()
                            else:
                                date = None
                            year = int(row.get('Year').value) if 'Year' in row else None
                            disco_entry = DiscoEntry(disco_page, row, type_=alb_type, lang=lang, date=date, year=year)
                            if isinstance(title, Link):
                                finder.add_entry_link(client, title, disco_entry)
                            elif isinstance(title, String):
                                finder.add_entry(disco_entry, row, False)
                            else:
                                links = list(title.find_all(Link, True))
                                if links:
                                    for link in links:
                                        finder.add_entry_link(client, link, disco_entry)
                                else:
                                    expected = type(title) is CompoundNode and isinstance(title[0], String)
                                    finder.add_entry(disco_entry, row, not expected)

        return finder.process_entries()


class DiscographyEntryFinder:
    """Internal-use class that handles common discography entry page discovery; used by Discography and Artist"""
    def __init__(self):
        self.found_page = defaultdict(lambda: False)
        self.remaining = Counter()
        self.entries_by_site = defaultdict(dict)
        self.no_link_entries = []

    def add_entry_link(self, client, link, disco_entry):
        self.remaining[disco_entry] += 1
        if link.interwiki:
            iw_key, iw_title = link.iw_key_title
            iw_client = client.interwiki_client(iw_key)
            self.entries_by_site[iw_client or client][iw_title if iw_client else link.title] = (disco_entry, link)
        else:
            self.entries_by_site[client][link.title] = (disco_entry, link)

    def add_entry(self, disco_entry, content, unexpected=True):
        self.no_link_entries.append(disco_entry)
        if unexpected:
            log.warning(f'Unexpected entry content: {content!r}')

    def process_entries(self):
        discography = []
        pages_by_site, errors_by_site = MediaWikiClient.get_multi_site_pages(self.entries_by_site)
        for site_client, title_entry_map in self.entries_by_site.items():
            for title, page in pages_by_site.get(site_client.host, {}).items():
                disco_entry, link = title_entry_map.pop(title)
                try:
                    discography.append(DiscographyEntry.from_page(page, disco_entry=disco_entry))
                except EntityTypeError as e:
                    self.remaining[disco_entry] -= 1
                    if self.found_page[disco_entry]:
                        log.log(9, f'Type mismatch for additional link={link} associated with {disco_entry}: {e}')
                    elif self.remaining[disco_entry]:
                        log.debug(f'{e}, but {self.remaining[disco_entry]} associated links are pending processing')
                    else:
                        log.warning(f'{e}, and no other links are available')

            for title, (disco_entry, link) in title_entry_map.items():
                log.debug(f'No page found for {link}')
                discography.append(DiscographyEntry(link.text or link.title, disco_entry=disco_entry))

        for disco_entry in self.no_link_entries:
            discography.append(DiscographyEntry(disco_entry=disco_entry))
        return discography
