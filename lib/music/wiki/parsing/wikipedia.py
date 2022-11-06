"""
:author: Doug Skrypa
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from copy import copy
from datetime import datetime, date
from functools import partial
from typing import TYPE_CHECKING, Iterator, Optional, Sequence, Iterable, Union, Any, Match

from ds_tools.caching.decorators import cached_property
from ds_tools.output import short_repr as _short_repr
from wiki_nodes.nodes import Template, Link, TableSeparator, CompoundNode, String, Node, Section, MappingNode, Table
from wiki_nodes.nodes import ContainerNode, AnyNode, Tag
from wiki_nodes.page import WikiPage

from music.common.disco_entry import DiscoEntryType
from music.text.extraction import split_enclosed, extract_enclosed
from music.text.name import Name
from music.text.time import parse_date
from music.text.utils import find_ordinal, title_case
from ..album import DiscographyEntry, DiscographyEntryEdition, DiscographyEntryPart
from ..base import TVSeries
from ..disco_entry import DiscoEntry
from ..discography import Discography
from .abc import WikiParser, EditionIterator
from .names import parse_track_artists
from .utils import PageIntro, RawTracks, LANG_ABBREV_MAP, find_language

if TYPE_CHECKING:
    from music.typing import OptStr
    from ..discography import DiscographyEntryFinder
    from ..typing import StrDateMap

__all__ = ['WikipediaParser']
log = logging.getLogger(__name__)

TrackRow = dict[str, Union[AnyNode, None, int]]

TRACK_LIST_SECTIONS = ('track list', 'tracklist', 'track listing')
IGNORE_SECTIONS = {
    'footnotes', 'references', 'music videos', 'see also', 'notes', 'videography', 'video albums', 'guest appearances',
    'other charted songs', 'other appearances'
}
short_repr = partial(_short_repr, containers_only=False)

DASH_LANG_SEARCH = re.compile(r'\b(\w+)-language\b', re.IGNORECASE).search


class WikipediaParser(WikiParser, site='en.wikipedia.org'):
    __slots__ = ()

    # region Artist Page

    def parse_artist_name(self, artist_page: WikiPage) -> Iterator[Name]:
        try:
            yield from PageIntro(artist_page).names()
        except ValueError as e:
            log.debug(e)
        yield Name(artist_page.title)

    def parse_group_members(self, artist_page: WikiPage) -> dict[str, list[str]]:
        raise NotImplementedError

    def parse_member_of(self, artist_page: WikiPage) -> Iterator[Link]:
        raise NotImplementedError

    # endregion

    # region Album Page

    def _album_page_name(self, page: WikiPage) -> Name:  # noqa
        if (names := list(PageIntro(page).names())) and len(names) > 0:
            # log.debug(f'Using name={names[0]!r} from page intro')
            return names[0]

        infobox = page.infobox
        try:
            name_str = infobox['name'].value
        except KeyError:
            pass
        else:
            if name_str and name_str[0] == name_str[-1] == '"':
                name_str = name_str[1:-1]
            if name_str:
                # log.debug(f'Using name={name_str!r} from infobox')
                return Name.from_enclosed(name_str)

        return Name(page.title)

    def parse_album_number(self, entry_page: WikiPage) -> Optional[int]:
        if intro := entry_page.intro():
            return find_ordinal(intro.raw.string)
        return None

    def process_album_editions(self, entry: DiscographyEntry, entry_page: WikiPage) -> EditionIterator:
        log.debug(f'Processing album editions for page={entry_page}')
        try:
            name = self._album_page_name(entry_page)
        except Exception as e:
            raise RuntimeError(f'Error parsing page name from {entry_page=}') from e

        yield from EditionFinder(name, entry, entry_page).editions()

    def process_edition_parts(self, edition: DiscographyEntryEdition) -> Iterator[DiscographyEntryPart]:
        content: WikipediaAlbumEditionPart | list[WikipediaAlbumEditionPart] = edition._content

        if isinstance(content, list):
            for edition_part in content:  # type: WikipediaAlbumEditionPart
                yield DiscographyEntryPart(edition_part.part_name, edition, RawWikipediaTracks(edition_part))
        elif content:
            yield DiscographyEntryPart(None, edition, RawWikipediaTracks(content))
        else:
            log.warning(f'Unexpected {content=} for {edition=}')

    def parse_track_name(self, row: TrackRow, edition_part: WikipediaAlbumEditionPart) -> Name:  # noqa
        return TrackNameParser(row, edition_part).parse_name()

    def parse_single_page_track_name(self, page: WikiPage) -> Name:
        raise NotImplementedError

    # endregion

    # region High Level Discography

    def process_disco_sections(self, artist_page: WikiPage, finder: DiscographyEntryFinder) -> None:
        try:
            section = artist_page.sections.find('Discography')
        except KeyError:
            log.debug(f'No discography section found for {artist_page}')
            return

        if not section.content:
            self._parse_disco_page_entries(artist_page, _disco_sections(section), finder)
            return
        try:
            disco_link_tmpl = section.content[0]
        except Exception as e:
            log.debug(f'Unexpected error finding the discography page link on {artist_page}: {e}')
            return

        if not (isinstance(disco_link_tmpl, Template) and disco_link_tmpl.name.lower() == 'main'):
            log.debug(f'Unexpected discography section format on {artist_page}')
            return

        try:
            disco_page_link = disco_link_tmpl.value
        except Exception as e:
            log.debug(f'Unexpected error finding the discography link on {artist_page} from {disco_link_tmpl}: {e}')
            return

        if not isinstance(disco_page_link, Link):
            if isinstance(disco_page_link, MappingNode):
                disco_page_link = Link.from_title(disco_page_link['1'].value, artist_page)
            elif isinstance(disco_page_link, list):
                disco_page_link = Link.from_title(disco_page_link[0].value, artist_page)
            else:
                log.debug(f'Unexpected {disco_page_link=} format on {artist_page}')
                return

        disco_entity = Discography.from_link(disco_page_link, artist=finder.artist)
        disco_entity._process_entries(finder)

    def parse_disco_page_entries(self, disco_page: WikiPage, finder: DiscographyEntryFinder) -> None:
        self._parse_disco_page_entries(disco_page, _disco_sections(disco_page.sections), finder)

    def _parse_disco_page_entries(self, page: WikiPage, sections: list[Section], finder: DiscographyEntryFinder):
        alb_types = []
        last_depth = -1
        for section in sections:
            if section.depth <= last_depth:
                alb_types.pop()
            last_depth = section.depth
            alb_types.append(section.title)
            lang = None

            content = section.content
            if not isinstance(content, Table):
                if isinstance(content, CompoundNode) and len(content) > 1 and isinstance(content[1], Table):
                    content = content[1]
                else:
                    log.debug(f'Unexpected content in {section=} on {page}: {content.__class__.__name__}')
                    continue

            try:
                self._parse_disco_page_entry_row(content, alb_types, lang, page, section, finder)
            except Exception:  # noqa
                log.error(f'Unexpected error processing {section=} on {page}:', exc_info=True, extra={'color': 9})

    def _parse_disco_page_entry_row(
        self, content, alb_types, lang, page: WikiPage, section: Section, finder: DiscographyEntryFinder
    ):
        for row in content:
            try:
                # log.debug(f'Processing alb_type={alb_types} row={row}')
                if isinstance(row, TableSeparator):
                    try:
                        lang = row.value.value
                    except AttributeError:  # Usually caused by a footnote about the table
                        pass
                else:
                    self._process_disco_row(page, finder, row, alb_types, lang)
            except TitleNotFound:
                log.debug(f'Unable to find title column in {section=} on {page} in row={short_repr(row)}')
                break  # Skip additional rows in this section
            except Exception:  # noqa
                log.error(
                    f'Error processing {section=} on {page} row={short_repr(row)}:', exc_info=True, extra={'color': 9}
                )

    def _process_disco_row(
        self, page: WikiPage, finder: DiscographyEntryFinder, row, alb_types: Sequence[str], lang: Optional[str]
    ) -> None:
        # TODO: re-released => repackage: https://en.wikipedia.org/wiki/Exo_discography
        if not (title := next(filter(None, (row.get(key) for key in ('Title', 'Song', ''))), None)):
            # Empty string example: https://en.wikipedia.org/wiki/AOA_discography#As_lead_artist
            # Song example: https://en.wikipedia.org/wiki/GWSN#Soundtrack_appearances
            raise TitleNotFound()

        track_data = None
        if details := next((row[key] for key in ('Details', 'Album details') if key in row), None):
            if track_list := details.find_one(Template, name='hidden'):
                try:
                    if track_list[0].value.lower() == 'track listing':
                        track_data = track_list[1]
                except Exception as e:
                    log.debug(f'Unexpected error extracting track list from disco row={row}: {e}')

            if details.__class__ is CompoundNode:
                details = details[0]
            details = details.as_dict(multiline=False)
            if date := details.get('Released', details.get('To be released')):
                if isinstance(date, String):
                    date = date.value
                elif date.__class__ is CompoundNode and isinstance(date[0], String):
                    date = date[0].value

                if '(' in date:
                    date = date.split('(', maxsplit=1)[0].strip()
        else:
            date = None

        year = int(row.get('Year').value) if 'Year' in row else None
        try:
            from_albums = node_to_link_dict(row.get('Album'))
        except ValueError as e:
            log.log(9, f'Error parsing album data from {page} for row={row.pformat()}: {e}')
            from_albums = None

        disco_entry = DiscoEntry(
            page, row, type_=alb_types, lang=lang, date=date, year=year, track_data=track_data, from_albums=from_albums
        )
        if isinstance(title, Link):
            finder.add_entry_link(title, disco_entry)
        elif isinstance(title, String):
            disco_entry.title = title.value             # TODO: cleanup templates, etc
            finder.add_entry(disco_entry, row, False)
        elif title is not None:  # it would not be None here anyways, but this makes PyCharm happy
            links = list(title.find_all(Link, True))
            if not finder.add_entry_links(links, disco_entry):
                expected = type(title) is CompoundNode and isinstance(title[0], String)
                if expected:
                    disco_entry.title = title[0].value
                finder.add_entry(disco_entry, row, not expected)

    # endregion

    # region Show / OST

    def parse_soundtrack_links(self, page: WikiPage) -> Iterator[Link]:
        raise NotImplementedError

    def parse_source_show(self, page: WikiPage) -> Optional[TVSeries]:
        raise NotImplementedError

    # endregion


class TrackNameParser:
    __slots__ = ('row', 'edition_part', 'extra')

    _remix_search = re.compile(r'\b(?:re)?mix\b', re.IGNORECASE).search
    _version_search = re.compile(r'\b(?:ver\.|version|dub)$', re.IGNORECASE).search
    _demo_search = re.compile(r'\bdemo\b', re.IGNORECASE).search

    def __init__(self, row: TrackRow, edition_part: WikipediaAlbumEditionPart):
        self.row = row
        self.edition_part = edition_part
        self.extra = {key: val for key, val in self._process_row_extras(row)}

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__}[row={self.row} in edition_part={self.edition_part!r}]>'

    def parse_name(self) -> Name:
        try:
            raw_title = self.row['title']
        except KeyError as e:
            raise RuntimeError(f'Missing title key for {self}') from e

        if isinstance(raw_title, Link):
            base = raw_title.show
        else:
            title = ' '.join(raw_title.strings())
            base, *after = split_enclosed(title, maxsplit=1)
            if after:
                self.extra.update(self._process_title_extras(after[0]))

        name = Name(base, extra=self.extra) if self.extra else Name(base)
        # log.debug(f'Parsed {name=} from {self}')
        return name

    def _process_title_extras(self, title_suffix: str) -> Iterator[tuple[str, Any]]:
        parts = [part.strip() for part in extract_enclosed(title_suffix.strip()).split('/')]
        for part in parts:
            yield self._classify_title_part(part)

    def _classify_title_part(self, part: str):
        # log.debug(f'_classify_title_part: {part!r}')
        lc_text = part.lower()
        if lc_text == 'live':
            return 'live', True
        elif lc_text.startswith(('inst.', 'instrumental')):
            return 'instrumental', True
        elif lc_text.startswith('acoustic'):
            if lc_text.endswith(('version', 'ver.')) and not lc_text[8:].strip().startswith('ver'):
                return 'version', part
            else:
                return 'acoustic', True
        elif lc_text.endswith('remaster'):
            return 'remaster', part
        elif lc_text.startswith(('feat.', 'featuring')):
            artists = part.split(maxsplit=1)[1]
            try:
                link_map = self.edition_part.section.root.link_map  # noqa
            except AttributeError:
                log.debug(f'No link_map found for {self}')
            else:
                artists = parse_track_artists(artists, link_map)
            return 'feat', artists
        elif lc_text.endswith(' only'):
            return 'availability', part
        elif self._remix_search(part):
            return 'remix', part
        elif self._version_search(part) or self._demo_search(part):
            return 'version', part
        else:
            log.debug(f'Unexpected wikipedia track title extra {part=}')
            return 'misc', part

    def _process_row_extras(self, row: TrackRow) -> Iterator[tuple[str, Any]]:
        try:
            yield 'length', next(iter(row['length'].strings()))
        except KeyError:
            pass

        if (extra_val := row.get('extra')) and self.edition_part.extra_column == 'artist':
            yield 'artists', extra_val

        try:
            note = ' '.join(row['note'].strings())
        except (KeyError, AttributeError):
            pass
        else:
            if note:
                yield self._classify_title_part(note)


class RawWikipediaTracks(RawTracks):
    __slots__ = ()
    raw_tracks: WikipediaAlbumEditionPart

    def get_names(self, part: DiscographyEntryPart, parser: WikipediaParser) -> list[Name]:
        raw_tracks = self.raw_tracks
        return [parser.parse_track_name(row, raw_tracks) for row in raw_tracks.tracks]


class EditionFinder:
    name: Name
    entry: DiscographyEntry
    entry_page: WikiPage

    def __init__(self, name: Name, entry: DiscographyEntry, entry_page: WikiPage):
        self.name = name
        self.entry = entry
        self.entry_page = entry_page

    def editions(self) -> EditionIterator:
        track_list_section = self.get_track_list_section()
        # log.debug(f'On page={self.entry_page}, found {track_list_section=}')
        if track_list_section is None:
            raise RuntimeError(f'Unable to find track list section on page={self.entry_page}')
        else:
            edition_parts = []
            self._process_section(track_list_section, False, edition_parts)
            for subsection in track_list_section:
                self._process_section(subsection, True, edition_parts)

            yield from self._group_edition_parts(edition_parts)

    def _process_section(self, section: Section, is_subsection: bool, edition_parts: list[WikipediaAlbumEditionPart]):
        if not (content := section.content):
            return
        elif isinstance(content, Template):
            edition_parts.append(self._process_template(section, content, is_subsection))
        elif isinstance(content, CompoundNode):
            for node in content:
                if isinstance(node, Template):
                    edition = self._process_template(section, node, is_subsection, edition_parts[:])  # Copy is required
                    edition_parts.append(edition)
                else:
                    log.debug(f'Ignoring node in {section=} of page={self.entry_page}: {node}')
        else:
            raise TypeError(f'Unexpected content in {section=} of page={self.entry_page}: {content}')

    def _group_edition_parts(self, edition_parts: list[WikipediaAlbumEditionPart]) -> EditionIterator:
        grouper = EditionGrouper(
            self.name,
            self.entry_page,
            self.entry,
            self.entry_type,
            self.artists,
            self.edition_date_map,
            self.languages,
            edition_parts,
        )
        yield from grouper.get_editions()

    def _process_template(
        self,
        section: Section,
        template: Template,
        is_subsection: bool,
        prev_eds: list[WikipediaAlbumEditionPart] = None,
    ) -> WikipediaAlbumEditionPart:
        if template.lc_name not in {'tracklist', 'track listing'}:
            raise ValueError(f'Unexpected track template={template.name!r} in {section=} on page={self.entry_page}')

        return WikipediaAlbumEditionPart(self.entry, self.entry_page, section, template, is_subsection, prev_eds)

    def get_track_list_section(self) -> Optional[Section]:
        root = self.entry_page.sections
        for key in TRACK_LIST_SECTIONS:
            try:
                return root.find_section(key, case_sensitive=False)
            except KeyError:
                pass
        return None

    @cached_property
    def edition_date_map(self) -> StrDateMap:
        try:
            released = self.entry_page.infobox['released']
        except (AttributeError, KeyError, TypeError):
            return {}
        try:
            value = released.value
        except AttributeError:
            pass
        else:
            if isinstance(value, datetime):
                return {None: value.date()}
            elif isinstance(value, date):
                return {None: value}

        released = '-'.join(released.strings())
        try:
            return {None: parse_date(released)}
        except (ValueError, TypeError) as e:
            log.warning(f'{e} from {released=} on page={self.entry_page}')
            return {}

    @cached_property
    def artists(self) -> set[Link]:
        if not (infobox := self.entry_page.infobox):
            return set()
        try:
            all_links = {link.title: link for link in self.entry_page.find_all(Link)}
        except Exception as e:
            raise RuntimeError(f'Error finding artist links for entry_page={self.entry_page}') from e

        artist_links = set()
        if artists := infobox.value.get('artist'):
            if isinstance(artists, String):
                artists_str = artists.value
                if artists_str.lower() not in ('various', 'various artists'):
                    for artist in map(str.strip, artists_str.split(', ')):
                        if artist.startswith('& '):
                            artist = artist[1:].strip()
                        if artist_link := all_links.get(artist):
                            artist_links.add(artist_link)
            elif isinstance(artists, Link):
                artist_links.add(artists)
            elif isinstance(artists, ContainerNode):
                for artist in artists:
                    if isinstance(artist, Link):
                        artist_links.add(artist)
                    elif isinstance(artist, String) and (artist_link := all_links.get(artist.value)):
                        artist_links.add(artist_link)
        return artist_links

    @cached_property
    def entry_type(self) -> DiscoEntryType:
        return DiscoEntryType.for_name(self.entry_page.categories)  # Note: 'type' is also in infobox sometimes

    @cached_property
    def languages(self) -> set[str]:
        """Languages specified in the album page's categories."""
        langs = set()
        for cat in self.entry_page.categories:
            if (m := DASH_LANG_SEARCH(cat)) and (lang := LANG_ABBREV_MAP.get(m.group(1))):
                langs.add(lang)
                break
        return langs


class EditionGrouper:
    def __init__(
        self,
        entry_name: Name,
        page: WikiPage,
        entry: DiscographyEntry,
        entry_type: DiscoEntryType,
        artists: set[Link],
        edition_date_map: StrDateMap,
        languages: set[str],
        edition_parts: list[WikipediaAlbumEditionPart],
    ):
        self.entry_name = entry_name
        self.page = page
        self.entry = entry
        self.entry_type = entry_type
        self.artists = artists
        self.edition_date_map = edition_date_map
        self.languages = languages
        self.edition_parts = edition_parts
        self._groups = defaultdict(list)

    def get_editions(self) -> EditionIterator:
        if len(self.edition_parts) == 1:
            yield self._edition(self.edition_parts[0])
        else:
            if not self._groups:
                self._group_editions()
            yield from (self._edition(group, name) for name, group in self._groups.items())
            # yield from self._old_group_iter()

    def _edition(
        self, content: WikipediaAlbumEditionPart | list[WikipediaAlbumEditionPart], edition: OptStr = None
    ) -> DiscographyEntryEdition:
        edition_part = content if isinstance(content, WikipediaAlbumEditionPart) else content[0]
        edition_obj = DiscographyEntryEdition(
            self.entry_name,
            self.page,
            self.entry,
            self.entry_type,
            self.artists,
            self.edition_date_map,
            content,
            edition or edition_part.name,
            edition_part.find_language(self.languages),
        )
        # log.debug(f'Created edition with name={self.entry_name} page={self.page} {edition=} {language=} {content=}')
        return edition_obj

    @cached_property
    def standard_edition_part(self) -> WikipediaAlbumEditionPart:
        return self.edition_parts[0]

    def _add_to_group(self, edition_part: WikipediaAlbumEditionPart):
        group = self._groups[edition_part.name]
        if not group and edition_part.disk != 1:
            group.append(self.standard_edition_part)

        group.append(edition_part)

    def _add_bonus_group(self, edition_part: WikipediaAlbumEditionPart):
        group_name = edition_part.name
        bonus_name = title_case(edition_part.bonus_disk_match.group(0))
        if group := self._groups[group_name]:
            self._groups[f'{group_name} + {bonus_name}'] = group = group[:]
        else:
            group.append(self.standard_edition_part)

        expected_disk = len(group) + 1
        if edition_part.disk != expected_disk:
            edition_part = copy(edition_part)
            edition_part.__dict__['disk'] = expected_disk

        group.append(edition_part)

    def _group_editions(self):
        bonus_disks = []
        for edition_part in self.edition_parts:
            if edition_part.bonus_disk_match:
                bonus_disks.append(edition_part)
            else:
                self._add_to_group(edition_part)

        for edition_part in bonus_disks:
            self._add_bonus_group(edition_part)

    # def _old_group_iter(self) -> EditionIterator:
    #     last: Optional[WikipediaAlbumEditionPart] = None
    #     group: list[WikipediaAlbumEditionPart] = []
    #     for edition_part in self.edition_parts:
    #         if edition_part.disk == 1:
    #             if group:
    #                 yield self._edition(group, last.name)
    #                 group = []
    #             elif last:
    #                 yield self._edition(last, last.name)
    #
    #             last = edition_part
    #         elif last and not group:
    #             if edition_part.bonus_disk_match:
    #                 yield self._edition(last, last.name)
    #                 group = [last, edition_part]
    #                 last = edition_part  # To use the bonus edition's name
    #             elif last.name == edition_part.name:
    #                 group = [last, edition_part]
    #             else:
    #                 yield self._edition(last, last.name)
    #                 group = [self.standard_edition_part, edition_part]
    #                 last = edition_part  # To use the new edition's name
    #         else:
    #             if not group:
    #                 group.append(last)
    #             group.append(edition_part)
    #
    #     if final := group or last:
    #         yield self._edition(final, last.name)


class WikipediaAlbumEditionPart:
    _suffix_match = re.compile(
        r'^(.*?)\b(?:'
        r'(?:CD )?bonus material|bonus (?:tracks|material|dis[ck]|vinyl)|track\s*list(?:ing)?'
        # r')$',
        r')\b.*',
        re.IGNORECASE,
    ).match
    _bonus_disk_search = re.compile(r'\bbonus\s+(?:dis[ck]|vinyl)\b', re.IGNORECASE).search
    _disk_search = re.compile(r'(?:CD|dis[ck])[:#. ]?(\d+)', re.IGNORECASE).search
    _edition_disk_part_match = re.compile(
        r'^(.*?)\s*(?:\s*[:-]\s*)?(?:CD|dis[ck])[:#. ]?(\d+)(?:\s*[:-]\s*)?(.*)$', re.IGNORECASE
    ).match
    meta: dict[str, AnyNode]
    _tracks: list[TrackRow]

    def __init__(
        self,
        entry: DiscographyEntry,
        entry_page: WikiPage,
        section: Section,
        template: Template,
        is_subsection: bool,
        prev_editions: list[WikipediaAlbumEditionPart] = None,
    ):
        self.entry = entry
        self.page = entry_page
        self.section = section
        self.template = template
        self.is_subsection = is_subsection
        self.prev_editions = prev_editions or []
        data = template.value
        self.meta = data['meta']
        self._tracks = data['tracks']

    def __repr__(self) -> str:
        section = self.section
        return (
            f'<{self.__class__.__name__}[{self.name!r}, disk={self.disk}]'
            f'[{section=} @ {section.root}, tracks={len(self.tracks)}]>'
        )

    @cached_property
    def album_name(self) -> str:
        return ' '.join(self.page.infobox['name'].strings())

    def _clean_name(self, name: OptStr) -> OptStr:
        if not name:
            return name
        an_len = len(self.album_name)
        if name.lower().startswith(self.album_name.lower()) and (len(name) == an_len or name[an_len] in ': '):
            name = name[an_len:].strip()
        if name.startswith((':', '-')):
            name = name[1:].strip()
        if not name:
            return None

        lc_name = name.lower()
        if lc_name.endswith('editions'):
            name = name[:-1]
        if m := self._suffix_match(name):
            name = m.group(1).strip()

        return name

    @cached_property
    def section_title(self) -> OptStr:
        if (title := self.section.title) and title.lower() not in TRACK_LIST_SECTIONS:
            return self._clean_name(title)
        return None

    @cached_property
    def name_and_part(self) -> tuple[OptStr, OptStr]:
        name = self.raw_name
        if (self.is_subsection or self.disk == 1 or not name) and self.section_title:
            name = self.section_title
        elif not (name := self._clean_name(name)):
            return None, None

        if m := self._edition_disk_part_match(name):
            name, _disk, part = m.groups()
        else:
            part = None

        return title_case(name), part

    @property
    def name(self) -> OptStr:
        return self.name_and_part[0]

    @cached_property
    def part_name(self) -> OptStr:
        return self.name_and_part[1] or f'CD{self.disk}'

    @cached_property
    def raw_name(self) -> OptStr:
        """The raw name from the edition/part track table header"""
        for key in ('header', 'headline'):
            if header := self.meta.get(key):
                if isinstance(header, CompoundNode):
                    nodes = (node for node in header if not isinstance(node, Tag) or node.name != 'ref')
                    return ' '.join(s for node in nodes for s in node.strings())
                return ' '.join(header.strings())
        return None

    def find_language(self, category_langs, lang: str = None):
        return find_language(self.template, lang, category_langs)

    @cached_property
    def disk(self) -> int:
        if (name := self.raw_name) and (m := self._disk_search(name)):
            return int(m.group(1))
        if self.bonus_disk_match:
            return 2  # TODO: This is not always accurate
        return 1

    @cached_property
    def bonus_disk_match(self) -> Optional[Match]:
        if name := self.raw_name:
            return self._bonus_disk_search(name)
        return None

    @cached_property
    def extra_column(self) -> OptStr:
        if not (extra_column := self.meta.get('extra_column')):
            return None
        return ' '.join(extra_column.strings()).lower()

    @cached_property
    def _first_num(self) -> int:
        return min(row['_num_'] for row in self._tracks)

    @cached_property
    def _last_num(self) -> int:
        return max(row['_num_'] for row in self._tracks)

    @cached_property
    def first_num(self) -> int:
        return min(row['_num_'] for row in self.tracks)

    @cached_property
    def last_num(self) -> int:
        return max(row['_num_'] for row in self.tracks)

    @cached_property
    def tracks(self) -> list[TrackRow]:
        if self._first_num > 1 and (prev_editions := self.prev_editions):
            expected_last = self._first_num - 1
            for edition in prev_editions[::-1]:
                if edition.last_num == expected_last:
                    return edition.tracks + self._tracks

            tracks = {row['_num_']: row for row in prev_editions[-1].tracks}
            tracks |= {row['_num_']: row for row in self._tracks}
            return list(tracks.values())

        return self._tracks


class TitleNotFound(Exception):
    """Exception that indicates a title column could not be found"""


def _disco_sections(section_iter: Iterable[Section]) -> list[Section]:
    sections = []
    for section in section_iter:
        if section.title.lower() in IGNORE_SECTIONS:
            break
        elif section.depth == 1:
            sections.extend(section)
        else:
            sections.append(section)
    return sections


def node_to_link_dict(node: Node) -> Optional[dict[str, Optional[Node]]]:
    if not node:
        return None
    elif not isinstance(node, Node):
        raise TypeError(f'Unexpected node type={node.__class__.__name__}')
    elif isinstance(node, Template) and node.lc_name == 'n/a':
        return None

    as_dict = {}
    if isinstance(node, String):
        as_dict[node.value] = None
    elif isinstance(node, Link):
        as_dict[node.show] = node
    elif isinstance(node, ContainerNode):
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
