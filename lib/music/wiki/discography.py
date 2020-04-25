"""
:author: Doug Skrypa
"""

import logging
from abc import ABC, abstractmethod
from collections import defaultdict, Counter
from typing import Dict, List, Iterable

from ds_tools.compat import cached_property
from wiki_nodes import MediaWikiClient, Link
from .album import DiscographyEntry
from .base import EntertainmentEntity
from .disco_entry import DiscoEntry
from .exceptions import EntityTypeError
from .utils import link_client_and_title

__all__ = ['Discography', 'DiscographyEntryFinder', 'DiscographyMixin']
log = logging.getLogger(__name__)


class DiscographyMixin(ABC):
    def __iter__(self):
        return iter(self.discography)

    @abstractmethod
    def _finder_with_entries(self) -> 'DiscographyEntryFinder':
        """
        Return a DiscographyEntryFinder instance that has DiscoEntry entries added, but has not yet processed links
        """
        raise NotImplementedError

    @cached_property
    def discography_entries(self) -> Dict[str, List[DiscographyEntry]]:
        return self._finder_with_entries().process_entries()

    @cached_property
    def discography(self) -> List[DiscographyEntry]:
        merged = []
        temp = defaultdict(list)
        for site, entries in self.discography_entries.items():
            for entry in entries:
                if not entry.name:
                    merged.append(entry)
                else:
                    temp[entry._merge_key].append(entry)

        for key, entries in temp.items():
            entries = iter(entries)
            entry = next(entries)
            for other in entries:
                entry._merge(other)
            merged.append(entry)
        return merged


class DiscographyEntryFinder:
    """Internal-use class that handles common discography entry page discovery; used by Discography and Artist"""
    def __init__(self):
        self.created_entry = defaultdict(lambda: False)
        self.remaining = Counter()
        self.entries_by_site = defaultdict(dict)
        self.no_link_entries = defaultdict(list)

    def add_entry_links(self, links: Iterable[Link], disco_entry: DiscoEntry):
        """
        :param iterable links: List or other iterable that yields :class:`Link<ds_tools.wiki.nodes.Link>` objects
        :param DiscoEntry disco_entry: The :class:`DiscoEntry<.music_manager.wiki.shared.DiscoEntry>` object for which
          links are being processed
        :return bool: True if entry links were added to be processed, False otherwise.  Allows this method to be used
          as a shortcut for adding the links and checking whether the entry had any links or not in the same call.
        """
        if links:
            for link in links:
                self.add_entry_link(link, disco_entry)
            return True
        return False

    def add_entry_link(self, link: Link, disco_entry: DiscoEntry):
        disco_entry.links.append(link)
        self.remaining[disco_entry] += 1
        mw_client, title = link_client_and_title(link)
        self.entries_by_site[mw_client][title] = (disco_entry, link)

    def add_entry(self, disco_entry: DiscoEntry, content, unexpected=True):
        self.no_link_entries[content.root.site].append(disco_entry)
        if unexpected:
            log.log(9, f'Unexpected entry content from {content.root}: {content!r}')

    def process_entries(self) -> Dict[str, List[DiscographyEntry]]:
        discography = defaultdict(list)
        pages_by_site, errors_by_site = MediaWikiClient.get_multi_site_pages(self.entries_by_site)
        for site_client, title_entry_map in self.entries_by_site.items():
            site = site_client.host
            for title, page in pages_by_site.get(site, {}).items():
                # log.debug(f'Found page with title={title!r} from site={site}')
                try:
                    disco_entry, link = title_entry_map.pop(title)
                except KeyError:
                    log.error(f'No disco entry was found for {title=!r} from {site=}', extra={'color': 9})
                    continue
                src_site = disco_entry.source.site
                try:
                    # log.debug(f'Creating DiscographyEntry for page={page} with entry={disco_entry}')
                    discography[src_site].append(DiscographyEntry.from_page(page, disco_entry=disco_entry))
                except EntityTypeError as e:
                    self.remaining[disco_entry] -= 1
                    if self.created_entry[disco_entry]:
                        log.log(9, f'Type mismatch for additional {link=} associated with {disco_entry}: {e}')
                    elif self.remaining[disco_entry]:
                        log.log(9, f'{e}, but {self.remaining[disco_entry]} associated links are pending processing')
                    else:
                        log.debug(f'{e}, and no other links are available')
                        # log.debug(f'Creating DiscographyEntry for page=[none found] entry={disco_entry}')
                        discography[src_site].append(DiscographyEntry.from_disco_entry(disco_entry))
                        self.created_entry[disco_entry] = True
                except Exception as e:
                    self.remaining[disco_entry] -= 1
                    msg = f'Unexpected error processing page={title!r} for {disco_entry=}:'
                    log.error(msg, exc_info=True, extra={'color': 9})
                else:
                    self.remaining[disco_entry] -= 1
                    self.created_entry[disco_entry] = True
                    disco_entry._link = link

            for title, (disco_entry, link) in title_entry_map.items():
                if not self.created_entry[disco_entry]:
                    log.log(9, f'No page found for {title=!r} / {link=} / entry={disco_entry}')
                    # log.debug(f'Creating DiscographyEntry for page=[none found] entry={disco_entry}')
                    discography[disco_entry.source.site].append(DiscographyEntry.from_disco_entry(disco_entry))
                    self.created_entry[disco_entry] = True

        for site, disco_entries in self.no_link_entries.items():
            site_discography = discography.setdefault(site, [])
            for disco_entry in disco_entries:
                if not self.created_entry[disco_entry]:
                    # log.debug(f'Creating DiscographyEntry for page=[no links] entry={disco_entry}')
                    site_discography.append(DiscographyEntry.from_disco_entry(disco_entry))
                    self.created_entry[disco_entry] = True
        return discography


class Discography(EntertainmentEntity, DiscographyMixin):
    """A discography page; not a collection of album objects."""
    _categories = ('discography', 'discographies')

    def _finder_with_entries(self) -> DiscographyEntryFinder:
        finder = DiscographyEntryFinder()
        self._process_entries(finder)
        return finder

    def _process_entries(self, finder: DiscographyEntryFinder):
        """
        Allows :meth:`Artist.discography_entries<.artist.Artist.discography_entries>` to add this page's entries to
        its own discovered discography entries
        """
        for page, parser in self.page_parsers('parse_disco_page_entries'):
            parser.parse_disco_page_entries(page, finder)
