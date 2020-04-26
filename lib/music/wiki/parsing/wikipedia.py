"""
:author: Doug Skrypa
"""

import logging
from functools import partial
from typing import TYPE_CHECKING, Iterator, Optional, List, Dict, Sequence, Iterable

from ds_tools.output import short_repr as _short_repr
from wiki_nodes import WikiPage, Template, Link, TableSeparator, CompoundNode, String, Node, Section, MappingNode
from wiki_nodes.nodes import N
from ...text import Name
from ..album import DiscographyEntry, DiscographyEntryEdition, DiscographyEntryPart
from ..disco_entry import DiscoEntry
from ..discography import Discography
from .abc import WikiParser, EditionIterator

if TYPE_CHECKING:
    from ..discography import DiscographyEntryFinder

__all__ = ['WikipediaParser']
log = logging.getLogger(__name__)

SECTION_BLACKLIST = {
    'footnotes', 'references', 'music videos', 'see also', 'notes', 'videography', 'video albums', 'guest appearances',
    'other charted songs', 'other appearances'
}
short_repr = partial(_short_repr, containers_only=False)


class WikipediaParser(WikiParser, site='en.wikipedia.org'):
    @classmethod
    def parse_artist_name(cls, artist_page: WikiPage) -> Iterator[Name]:
        raise NotImplementedError

    @classmethod
    def parse_album_name(cls, node: N) -> Name:
        raise NotImplementedError

    @classmethod
    def parse_album_number(cls, entry_page: WikiPage) -> Optional[int]:
        raise NotImplementedError

    @classmethod
    def parse_track_name(cls, node: N) -> Name:
        raise NotImplementedError

    @classmethod
    def process_disco_sections(cls, artist_page: WikiPage, finder: 'DiscographyEntryFinder') -> None:
        try:
            section = artist_page.sections.find('Discography')
        except KeyError:
            log.debug(f'No discography section found for {artist_page}')
            return

        if section.content:
            try:
                disco_link_tmpl = section.content[0]
            except Exception as e:
                log.debug(f'Unexpected error finding the discography page link on {artist_page}: {e}')
                return

            if isinstance(disco_link_tmpl, Template) and disco_link_tmpl.name.lower() == 'main':
                try:
                    disco_page_link = disco_link_tmpl.value
                except Exception as e:
                    log.debug(
                        f'Unexpected error finding the discography link on {artist_page} from {disco_link_tmpl}: {e}'
                    )
                else:
                    if not isinstance(disco_page_link, Link):
                        if isinstance(disco_page_link, MappingNode):
                            disco_page_link = Link.from_title(disco_page_link['1'].value, artist_page)
                        else:
                            log.debug(f'Unexpected {disco_page_link=} format on {artist_page}')
                            return

                    disco_entity = Discography.from_link(disco_page_link)
                    disco_entity._process_entries(finder)
            else:
                log.debug(f'Unexpected discography section format on {artist_page}')
        else:
            cls._parse_disco_page_entries(artist_page, _disco_sections(section), finder)

    @classmethod
    def process_album_editions(cls, entry: 'DiscographyEntry', entry_page: WikiPage) -> EditionIterator:
        raise NotImplementedError

    @classmethod
    def process_edition_parts(cls, edition: 'DiscographyEntryEdition') -> Iterator['DiscographyEntryPart']:
        raise NotImplementedError

    @classmethod
    def parse_group_members(cls, artist_page: WikiPage) -> Dict[str, List[str]]:
        raise NotImplementedError

    @classmethod
    def parse_member_of(cls, artist_page: WikiPage) -> Iterator[Link]:
        raise NotImplementedError

    @classmethod
    def parse_disco_page_entries(cls, disco_page: WikiPage, finder: 'DiscographyEntryFinder') -> None:
        cls._parse_disco_page_entries(disco_page, _disco_sections(disco_page.sections), finder)

    @classmethod
    def _parse_disco_page_entries(cls, page: WikiPage, sections: List[Section], finder: 'DiscographyEntryFinder'):
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
                        # log.debug(f'Processing alb_type={alb_types} row={row}')
                        if isinstance(row, TableSeparator):
                            try:
                                lang = row.value.value
                            except AttributeError:  # Usually caused by a footnote about the table
                                pass
                        else:
                            cls._process_disco_row(page, finder, row, alb_types, lang)
                    except Exception:
                        log.error(f'Error processing {section=} row={short_repr(row)}:', exc_info=True, extra={'color': 9})
            except Exception:
                log.error(f'Unexpected error processing {section=}:', exc_info=True, extra={'color': 9})

    @classmethod
    def _process_disco_row(
            cls, page: WikiPage, finder: 'DiscographyEntryFinder', row, alb_types: Sequence[str],
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
        try:
            from_albums = node_to_link_dict(row.get('Album'))
        except ValueError as e:
            log.debug(f'Error parsing album data for {row=}: {e}')
            from_albums = None

        disco_entry = DiscoEntry(
            page, row, type_=alb_types, lang=lang, date=date, year=year, track_data=track_data, from_albums=from_albums
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


def _disco_sections(section_iter: Iterable[Section]) -> List[Section]:
    sections = []
    for section in section_iter:
        if section.title.lower() in SECTION_BLACKLIST:
            break
        elif section.depth == 1:
            sections.extend(section)
        else:
            sections.append(section)
    return sections


def node_to_link_dict(node: Node) -> Optional[Dict[str, Optional[Node]]]:
    if not node:
        return None
    elif not isinstance(node, Node):
        raise TypeError(f'Unexpected node type={node.__class__.__name__}')
    elif isinstance(node, Template) and node.name.lower() == 'n/a':
        return None

    as_dict = {}
    if isinstance(node, String):
        as_dict[node.value] = None
    elif isinstance(node, Link):
        as_dict[node.show] = node
    elif isinstance(node, CompoundNode):
        if len(node) == 2:
            a, b = node
            if isinstance(a, Link) and isinstance(b, String):
                if b.value == 'OST' or (b.value.startswith('OST') and 'part' in b.value.lower()):
                    as_dict[f'{a.show} {b.value}'] = a
                elif b.value.startswith('and '):
                    as_dict[a.show] = a
                    as_dict[b.value[4:].strip()] = None
                else:
                    raise ValueError(f'Unexpected content for {node=}')
            elif isinstance(a, String) and isinstance(b, Link):
                if a.value.endswith(' and'):
                    as_dict[b.show] = b
                    as_dict[a.value[:-4].strip()] = None
                else:
                    raise ValueError(f'Unexpected content for {node=}')
        elif len(node) == 3:
            a, b, c = node
            if isinstance(a, Link) and isinstance(b, String) and isinstance(c, Link):
                b = b.value
                if b.startswith('OST '):
                    as_dict[f'{a.show} OST'] = a
                    b = b[4:].strip()
                else:
                    as_dict[a.show] = a
                if b == 'and':
                    as_dict[c.show] = c
                else:
                    raise ValueError(f'Unexpected content for {node=}')
            elif isinstance(a, String) and isinstance(b, Link) and isinstance(c, String):
                a, c = map(lambda n: n.value.strip("'"), (a, c))
                if not a and c == 'OST':
                    as_dict[f'{b.show} OST'] = b
                else:
                    raise ValueError(f'Unexpected content for {node=}')
            else:
                raise ValueError(f'Unexpected content for {node=}')
    else:
        raise ValueError(f'Unexpected content for {node=}')

    for to_rm in ('Non-album single', 'Non-album singles'):
        if to_rm in as_dict:
            del as_dict[to_rm]

    return as_dict
