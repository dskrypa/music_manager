"""
:author: Doug Skrypa
"""

import logging
from abc import ABC, abstractmethod
from collections import defaultdict, Counter
from traceback import format_exc

from ds_tools.compat import cached_property
from ds_tools.wiki.http import MediaWikiClient
from ds_tools.wiki.nodes import Link, String, CompoundNode, TableSeparator, Template, MixedNode
from .album import DiscographyEntry
from .base import WikiEntity
from .disco_entry import DiscoEntry
from .exceptions import EntityTypeError
from .utils import node_to_link_dict

__all__ = ['Discography', 'DiscographyEntryFinder', 'DiscographyMixin']
log = logging.getLogger(__name__)


class DiscographyMixin(ABC):
    @abstractmethod
    def _finder_with_entries(self):
        """
        Return a DiscographyEntryFinder instance that has DiscoEntry entries added, but has not yet processed links
        """
        raise NotImplementedError

    @cached_property
    def discography_entries(self):
        return self._finder_with_entries().process_entries()

    @cached_property
    def discography(self):
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


def short_repr(obj, max_len=100):
    obj_repr = repr(obj)
    if len(obj_repr) <= max_len:
        return obj_repr
    pos = max_len // 2
    return f'{obj_repr[:pos]}...{obj_repr[-pos:]}'


class Discography(WikiEntity, DiscographyMixin):
    """A discography page; not a collection of album objects."""
    _categories = ('discography', 'discographies')

    def _finder_with_entries(self):
        finder = DiscographyEntryFinder()
        self._process_entries(finder)
        return finder

    def _process_entries(self, finder):
        """
        Allows :meth:`Artist.discography_entries<.artist.Artist.discography_entries>` to add this page's entries to
        its own discovered discography entries
        """
        for site, disco_page in self._pages.items():
            client = MediaWikiClient(site)
            if site == 'en.wikipedia.org':
                blacklist = {
                    'footnotes', 'references', 'music videos', 'see also', 'notes', 'videography', 'video albums'
                }
                sections = []
                for section in disco_page.sections:
                    if section.title.lower() in blacklist:
                        break
                    elif section.depth == 1:
                        sections.extend(section)
                    else:
                        sections.append(section)

                alb_types = []
                last_depth = -1
                for section in sections:
                    if section.depth <= last_depth:
                        alb_types.pop()
                    last_depth = section.depth
                    alb_types.append(section.title)
                    lang = None
                    try:
                        for row in section.content:
                            try:
                                # log.debug(f'Processing alb_type={alb_type} row={row}')
                                if isinstance(row, TableSeparator):
                                    try:
                                        lang = row.value.value
                                    except AttributeError:      # Usually caused by a footnote about the table
                                        pass
                                else:
                                    self._process_wikipedia_row(client, disco_page, finder, row, alb_types, lang)
                            except Exception as e:
                                # log.error(f'Unexpected error processing section={section} row={short_repr(row)}: {e}')
                                log.error(f'Unexpected error processing section={section} row={short_repr(row)}:\n{format_exc()}', extra={'color': 'red'})
                    except Exception as e:
                        log.error(f'Unexpected error processing section={section}: {format_exc()}', extra={'color': 'red'})

    # noinspection PyMethodMayBeStatic
    def _process_wikipedia_row(self, client, disco_page, finder, row, alb_types, lang):
        title = row['Title']
        track_data = None
        details = next((row[key] for key in ('Details', 'Album details') if key in row), None)
        if details is not None:
            track_list = details.find_one(Template, name='hidden')
            if track_list is not None:
                try:
                    if track_list[0].value.lower() == 'track listing':
                        track_data = track_list[1]
                except Exception as e:
                    log.debug(f'Unexpected error extracting track list from disco row={row}: {e}')

            if type(details) is CompoundNode:
                details = details[0]
            details = details.as_dict()
            date = details.get('Released', details.get('To be released'))
            if date is not None:
                if isinstance(date, String):
                    date = date.value
                elif type(date) is CompoundNode and isinstance(date[0], String):
                    date = date[0].value

                if '(' in date:
                    date = date.split('(', maxsplit=1)[0].strip()
        else:
            date = None

        year = int(row.get('Year').value) if 'Year' in row else None
        disco_entry = DiscoEntry(
            disco_page, row, type_=alb_types, lang=lang, date=date, year=year, track_data=track_data,
            from_albums=row.get('Album')
        )
        if isinstance(title, Link):
            finder.add_entry_link(client, title, disco_entry)
        elif isinstance(title, String):
            disco_entry.title = title.value             # TODO: cleanup templates, etc
            finder.add_entry(disco_entry, row, False)
        else:
            links = list(title.find_all(Link, True))
            if not finder.add_entry_links(client, links, disco_entry):
                expected = type(title) is CompoundNode and isinstance(title[0], String)
                if expected:
                    disco_entry.title = title[0].value
                finder.add_entry(disco_entry, row, not expected)


class DiscographyEntryFinder:
    """Internal-use class that handles common discography entry page discovery; used by Discography and Artist"""
    def __init__(self):
        self.found_page = defaultdict(lambda: False)
        self.remaining = Counter()
        self.entries_by_site = defaultdict(dict)
        self.no_link_entries = defaultdict(list)

    def add_entry_links(self, client, links, disco_entry):
        """
        :param MediaWikiClient client: The :class:`MediaWikiClient<ds_tools.wiki.http.MediaWikiClient>` associated with
          the source of the given disco_entry
        :param iterable links: List or other iterable that yields :class:`Link<ds_tools.wiki.nodes.Link>` objects
        :param DiscoEntry disco_entry: The :class:`DiscoEntry<.music_manager.wiki.shared.DiscoEntry>` object for which
          links are being processed
        :return bool: True if entry links were added to be processed, False otherwise.  Allows this method to be used
          as a shortcut for adding the links and checking whether the entry had any links or not in the same call.
        """
        if links:
            for link in links:
                self.add_entry_link(client, link, disco_entry)
            return True
        return False

    def add_entry_link(self, client, link, disco_entry):
        disco_entry.links.append(link)
        self.remaining[disco_entry] += 1
        if link.interwiki:
            iw_key, iw_title = link.iw_key_title
            iw_client = client.interwiki_client(iw_key)
            self.entries_by_site[iw_client or client][iw_title if iw_client else link.title] = (disco_entry, link)
        else:
            self.entries_by_site[client][link.title] = (disco_entry, link)

    def add_entry(self, disco_entry, content, unexpected=True):
        self.no_link_entries[content.root.site].append(disco_entry)
        if unexpected:
            log.log(9, f'Unexpected entry content from {content.root}: {content!r}')

    def process_entries(self):
        discography = {}
        pages_by_site, errors_by_site = MediaWikiClient.get_multi_site_pages(self.entries_by_site)
        for site_client, title_entry_map in self.entries_by_site.items():
            site = site_client.host
            discography[site] = []
            for title, page in pages_by_site.get(site, {}).items():
                try:
                    disco_entry, link = title_entry_map.pop(title)
                except KeyError:
                    msg = f'No disco entry was found for title={title!r} from site={site}'
                    log.error(msg, extra={'color': 'red'})
                    continue

                try:
                    discography[site].append(DiscographyEntry.from_page(page, disco_entry=disco_entry))
                except EntityTypeError as e:
                    self.remaining[disco_entry] -= 1
                    if self.found_page[disco_entry]:
                        log.log(9, f'Type mismatch for additional link={link} associated with {disco_entry}: {e}')
                    elif self.remaining[disco_entry]:
                        log.log(9, f'{e}, but {self.remaining[disco_entry]} associated links are pending processing')
                    else:
                        log.warning(f'{e}, and no other links are available')
                except Exception as e:
                    msg = f'Unexpected error processing page={title!r} for disco_entry={disco_entry}: {format_exc()}'
                    log.error(msg, extra={'color': 'red'})
                else:
                    disco_entry._link = link

            for title, (disco_entry, link) in title_entry_map.items():
                log.log(9, f'No page found for {link}')
                discography[site].append(DiscographyEntry.from_disco_entry(disco_entry))

        for site, disco_entries in self.no_link_entries.items():
            site_discography = discography.setdefault(site, [])
            for disco_entry in disco_entries:
                site_discography.append(DiscographyEntry.from_disco_entry(disco_entry))
        return discography
