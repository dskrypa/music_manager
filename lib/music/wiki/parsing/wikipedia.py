"""
:author: Doug Skrypa
"""

import logging
from functools import partial
from typing import TYPE_CHECKING, Iterator, Optional, List, Dict, Sequence

from ds_tools.output import short_repr as _short_repr
from wiki_nodes import WikiPage, Node, Template, Link, TableSeparator, CompoundNode, String
from ...text import Name
from ..album import DiscographyEntry, DiscographyEntryEdition
from ..disco_entry import DiscoEntry
from ..discography import Discography
from .abc import WikiParser, EditionIterator

if TYPE_CHECKING:
    from ..discography import DiscographyEntryFinder

__all__ = ['WikipediaParser']
log = logging.getLogger(__name__)

short_repr = partial(_short_repr, containers_only=False)


class WikipediaParser(WikiParser, site='en.wikipedia.org'):
    @classmethod
    def parse_artist_name(cls, artist_page: WikiPage) -> Iterator[Name]:
        raise NotImplementedError

    @classmethod
    def parse_album_name(cls, node: Node) -> Name:
        raise NotImplementedError

    @classmethod
    def parse_album_number(cls, entry_page: WikiPage) -> Optional[int]:
        raise NotImplementedError

    @classmethod
    def parse_track_name(cls, node: Node) -> Name:
        raise NotImplementedError

    @classmethod
    def process_disco_sections(cls, artist_page: WikiPage, finder: 'DiscographyEntryFinder') -> None:
        try:
            section = artist_page.sections.find('Discography')
        except KeyError:
            log.debug(f'No discography section found for {artist_page}')
            return
        try:
            disco_page_link_tmpl = section.content[0]
        except Exception as e:
            log.debug(f'Unexpected error finding the discography page link on {artist_page}: {e}')
            return

        if isinstance(disco_page_link_tmpl, Template) and disco_page_link_tmpl.name.lower() == 'main':
            try:
                disco_page_title = disco_page_link_tmpl.value[0].value
            except Exception as e:
                log.debug(f'Unexpected error finding the discography page link on {artist_page}: {e}')
            else:
                disco_entity = Discography.from_page(cls.client.get_page(disco_page_title))
                disco_entity._process_entries(finder)
        else:
            log.debug(f'Unexpected discography section format on {artist_page}')

    @classmethod
    def process_album_editions(cls, entry: 'DiscographyEntry', entry_page: WikiPage) -> EditionIterator:
        raise NotImplementedError

    @classmethod
    def parse_group_members(cls, artist_page: WikiPage) -> Dict[str, List[str]]:
        raise NotImplementedError

    @classmethod
    def parse_member_of(cls, artist_page: WikiPage) -> Iterator[Link]:
        raise NotImplementedError

    @classmethod
    def parse_disco_page_entries(cls, disco_page: WikiPage, finder: 'DiscographyEntryFinder') -> None:
        blacklist = {'footnotes', 'references', 'music videos', 'see also', 'notes', 'videography', 'video albums'}
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
                            except AttributeError:  # Usually caused by a footnote about the table
                                pass
                        else:
                            cls._process_disco_row(disco_page, finder, row, alb_types, lang)
                    except Exception:
                        log.error(f'Error processing {section=} row={short_repr(row)}:', exc_info=True, extra={'color': 9})
            except Exception:
                log.error(f'Unexpected error processing {section=}:', exc_info=True, extra={'color': 9})

    @classmethod
    def _process_disco_row(
            cls, disco_page: WikiPage, finder: 'DiscographyEntryFinder', row, alb_types: Sequence[str],
            lang: Optional[str]
    ) -> None:
        # TODO: re-released => repackage: https://en.wikipedia.org/wiki/Exo_discography
        title = row['Title']
        track_data = None
        if details := next((row[key] for key in ('Details', 'Album details') if key in row), None):
            if track_list := details.find_one(Template, name='hidden'):
                try:
                    if track_list[0].value.lower() == 'track listing':
                        track_data = track_list[1]
                except Exception as e:
                    log.debug(f'Unexpected error extracting track list from disco row={row}: {e}')

            if type(details) is CompoundNode:
                details = details[0]
            details = details.as_dict(multiline=False)
            if date := details.get('Released', details.get('To be released')):
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
            finder.add_entry_link(title, disco_entry)
        elif isinstance(title, String):
            disco_entry.title = title.value             # TODO: cleanup templates, etc
            finder.add_entry(disco_entry, row, False)
        else:
            links = list(title.find_all(Link, True))
            if not finder.add_entry_links(links, disco_entry):
                expected = type(title) is CompoundNode and isinstance(title[0], String)
                if expected:
                    disco_entry.title = title[0].value
                finder.add_entry(disco_entry, row, not expected)
