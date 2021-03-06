"""
:author: Doug Skrypa
"""

import logging
import re
from datetime import datetime, date
from typing import TYPE_CHECKING, Iterator, Optional, List, Dict, Set, Any, Tuple, Union, Type

from ds_tools.unicode import LangCat
from wiki_nodes import (
    WikiPage, Link, String, CompoundNode, Section, Table, MappingNode, TableSeparator, Template, Tag, List as ListNode
)
from wiki_nodes.nodes import N, AnyNode
from ...common.disco_entry import DiscoEntryType
from ...text.extraction import split_enclosed, ends_with_enclosed, has_unpaired
from ...text.name import Name
from ...text.time import parse_date
from ...text.utils import combine_with_parens, find_ordinal
from ..album import DiscographyEntry, DiscographyEntryEdition, DiscographyEntryPart
from ..base import EntertainmentEntity, GROUP_CATEGORIES, TVSeries
from ..disco_entry import DiscoEntry
from ..exceptions import SiteDoesNotExist
from .abc import WikiParser, EditionIterator
from .utils import name_from_intro, get_artist_title, LANG_ABBREV_MAP, find_language

if TYPE_CHECKING:
    from ..discography import DiscographyEntryFinder

__all__ = ['KpopFandomParser', 'KindieFandomParser']
log = logging.getLogger(__name__)

NodeTypes = Union[Type[AnyNode], Tuple[Type[AnyNode], ...]]

DURATION_MATCH = re.compile(r'^(.*?)-\s*(\d+:\d{2})(.*)$').match
MEMBER_TYPE_SECTIONS = {'former': 'Former', 'inactive': 'Inactive', 'sub_units': 'Sub-Units'}
ORD_ALBUM_MATCH = re.compile(r'^\S+(?:st|nd|rd|th)\s+album:?$', re.IGNORECASE).match
RELEASE_DATE_FINDITER = re.compile(r'((?:[a-z]+(?: \d+)?, )?\d{4})', re.IGNORECASE).finditer
REMAINDER_ARTIST_EXTRA_TYPE_MAP = {'(': 'artists', '(feat.': 'feat', '(sung by': 'artists', '(with': 'collabs'}
UNCLOSED_PAREN_MATCH = re.compile(r'^(.+?)(\([^()]*)$').match
VERSION_SEARCH = re.compile(r'^(.*?(?<!\S)ver(?:\.|sion)?)\)?(.*)$', re.IGNORECASE).match


class KpopFandomParser(WikiParser, site='kpop.fandom.com', domain='fandom.com'):
    @classmethod
    def parse_artist_name(cls, artist_page: WikiPage) -> Iterator[Name]:
        yield from name_from_intro(artist_page)
        if _infobox := artist_page.infobox:
            # log.debug(f'Found infobox for {artist_page}')
            infobox = _infobox.value
            if birth_name := infobox.get('birth_name'):
                if isinstance(birth_name, String):
                    yield Name.from_enclosed(birth_name.value)
                elif isinstance(birth_name, CompoundNode):
                    for line in birth_name:
                        if isinstance(line, String):
                            yield Name.from_enclosed(line.value)
                else:
                    raise ValueError(f'Unexpected format for birth_name={birth_name.pformat()}')
            else:
                eng = eng.value if (eng := infobox.get('name')) else None
                non_eng_vals = []
                for script in ('hangul', 'hanja', 'hiragana', 'kanji'):
                    if node := infobox.get(script):
                        if isinstance(node, String):
                            non_eng_vals.append((script, node.value))
                        elif isinstance(node, CompoundNode):    # Example: GWSN - Kanji with Japanese + Chinese
                            for sub_node in node:
                                if isinstance(sub_node, String):
                                    non_eng_vals.append((script, sub_node.value))
                        else:
                            log.debug(f'Unexpected alt lang name node type on {artist_page}: {script}={node!r}')

                if eng or non_eng_vals:
                    non_eng = non_eng_vals.pop(0)[1] if non_eng_vals else None
                    yield Name(eng, non_eng, versions={Name(eng, val[1]) for val in non_eng_vals})
        else:
            log.debug(f'No infobox found for {artist_page}')

    @classmethod
    def parse_album_name(cls, node: N) -> Name:
        # For discography page/section entries
        raise NotImplementedError

    @classmethod
    def parse_album_number(cls, entry_page: WikiPage) -> Optional[int]:
        if intro := entry_page.intro():
            return find_ordinal(intro.raw.string)
        return None

    @classmethod
    def process_disco_sections(cls, artist_page: WikiPage, finder: 'DiscographyEntryFinder') -> None:
        try:
            section = artist_page.sections.find('Discography')
        except KeyError:
            return

        err_msg = f'Unexpected error processing {section=} on {artist_page}'
        if section.depth == 1:
            for alb_type, alb_type_section in section.children.items():
                if alb_type.lower().startswith('dvd'):
                    log.debug(f'Skipping {alb_type=!r}')
                    continue
                try:
                    cls._process_disco_section(artist_page, finder, alb_type_section, alb_type)
                except Exception as e:
                    log.error(err_msg, exc_info=True, extra={'color': 'red'})
        elif section.depth == 2:  # key = language, value = sub-section
            for lang, lang_section in section.children.items():
                for alb_type, alb_type_section in lang_section.children.items():
                    if alb_type.lower().startswith('dvd'):
                        log.debug(f'Skipping {alb_type=!r}')
                        continue
                    # log.debug(f'{alb_type}: {alb_type_section.content}')
                    try:
                        cls._process_disco_section(artist_page, finder, alb_type_section, alb_type, lang)
                    except Exception as e:
                        log.error(err_msg, exc_info=True, extra={'color': 'red'})
        else:
            log.warning(f'Unexpected section depth: {section.depth} on {artist_page}')

    @classmethod
    def _process_disco_section(
            cls, artist_page: WikiPage, finder: 'DiscographyEntryFinder', section: Section, alb_type: str,
            lang: Optional[str] = None
    ) -> None:
        content = section.content
        # log.debug(f'Processing {section=} on {artist_page}:\n{content.pformat()}')
        if type(content) is CompoundNode:   # A template for splitting the discography into
            content = content[0]            # columns follows the list of albums in this section

        if not isinstance(content, ListNode):
            try:
                raise TypeError(f'Unexpected content on {artist_page}: {content.pformat()}')
            except AttributeError:
                raise TypeError(f'Unexpected content on {artist_page}: {content!r}')

        for entry in content.iter_flat():
            # log.debug(f'Processing {artist_page} {entry=!r}')
            # {primary artist} - {album or single} [(with collabs)] (year)
            if isinstance(entry, String):
                entry_str = entry.value
                year_str = entry_str.rsplit(maxsplit=1)[1]
            else:
                entry_str = None
                try:
                    entry_str = entry[-1].value
                    year_str = entry_str.rsplit(maxsplit=1)[-1]
                except AttributeError:
                    log.debug(f'Unable to parse year from {entry=!r} on {artist_page}')
                    year_str = None

            try:
                year = datetime.strptime(year_str, '(%Y)').year if year_str else 0
            except ValueError:
                if entry_str and ORD_ALBUM_MATCH(entry_str):
                    continue
                else:
                    log.warning(f'Unexpected disco {entry=!r} on {artist_page}', extra={'color': 'red'})
            else:
                disco_entry = DiscoEntry(artist_page, entry, type_=alb_type, lang=lang, year=year)
                if isinstance(entry, CompoundNode):
                    links = list(entry.find_all(Link, True))
                    if alb_type == 'Features':
                        # {primary artist} - {album or single} [(with collabs)] (year)
                        if isinstance(entry[1], String):
                            entry_1 = entry[1].value.strip()
                            if entry_1 == '-' and cls._check_type(entry, 2, Link):
                                link = entry[2]
                                links = [link]
                                disco_entry.title = link.show
                            elif entry_1.startswith('-'):
                                disco_entry.title = entry_1[1:].strip(' "')
                        elif isinstance(entry[1], Link):
                            disco_entry.title = entry[1].show
                    else:
                        if isinstance(entry[0], Link):
                            disco_entry.title = entry[0].show
                        elif isinstance(entry[0], String):
                            disco_entry.title = entry[0].value.strip(' "')

                    if links:
                        for link in links:
                            try:
                                finder.add_entry_link(link, disco_entry)
                            except SiteDoesNotExist:
                                log.log(19, f'Found bad {link=!r} on {artist_page=!r} in {section=!r}')
                    else:
                        finder.add_entry(disco_entry, entry)
                elif isinstance(entry, String):
                    disco_entry.title = entry.value.split('(')[0].strip(' "')
                    finder.add_entry(disco_entry, entry)
                else:
                    log.warning(f'On page={artist_page}, unexpected type for {entry=!r}')

    @classmethod
    def _album_page_name(cls, page: WikiPage) -> Name:
        if (names := list(name_from_intro(page))) and len(names) > 0:
            return names[0]
        else:
            infobox = page.infobox
            try:
                return Name.from_enclosed(infobox['name'].value)
            except KeyError:
                return Name(page.title)

    @classmethod
    def process_album_editions(cls, entry: 'DiscographyEntry', entry_page: WikiPage) -> EditionIterator:
        try:
            name = cls._album_page_name(entry_page)
        except Exception as e:
            raise RuntimeError(f'Error parsing page name from {entry_page=}') from e
        infobox = entry_page.infobox
        repackage_page = (alb_type := infobox.value.get('type')) and alb_type.value.lower() == 'repackage'
        if name.extra:
            repackage_page = repackage_page or name.extra.get('repackage', False)
        entry_type = DiscoEntryType.for_name(entry_page.categories)     # Note: 'type' is also in infobox sometimes
        artists = _find_artist_links(infobox, entry_page)
        try:
            dates = _find_release_dates(infobox)
        except ValueError as e:
            log.error(f'Error parsing date on {entry_page=!r}: {e}')
            dates = []
        langs = _find_page_languages(entry_page)

        tl_keys = ('Track list', 'Tracklist')
        if track_list_section := next(filter(None, (entry_page.sections.find(key, None) for key in tl_keys)), None):
            orig = track_list_section.pformat('content')
            try:
                track_section_content = track_list_section.processed(False, False, False, False, True)
            except Exception:
                log.error(f'Error processing track list on {entry_page}:\n{orig}', exc_info=True)
                return

            if track_section_content:
                yield DiscographyEntryEdition(  # edition or version = None
                    name, entry_page, entry, entry_type, artists, dates, track_section_content, None,
                    find_language(track_section_content, None, langs), repackage_page
                )

            discs = []
            for section in track_list_section:
                title = section.title
                lc_title = title.lower()
                if lc_title == 'cd':
                    yield DiscographyEntryEdition(  # edition or version = None
                        name, entry_page, entry, entry_type, artists, dates, section.content, None,
                        find_language(section.content, None, langs), repackage_page
                    )
                elif lc_title.startswith(('cd', 'disc', 'disk')):
                    discs.append((section.content, find_language(section.content, None, langs)))
                elif not lc_title.startswith('dvd'):
                    edition, lang = _process_album_version(title)
                    yield DiscographyEntryEdition(
                        name, entry_page, entry, entry_type, artists, dates, section.content, edition,
                        find_language(section.content, lang, langs), repackage_page
                    )

            if discs:
                ed_lang = None
                if ed_langs := set(filter(None, {disc[1] for disc in discs})):
                    if not (ed_lang := next(iter(ed_langs)) if len(ed_langs) == 1 else None):
                        log.debug(f'Found multiple languages for {entry_page} discs: {ed_langs}')

                yield DiscographyEntryEdition(  # edition or version = None
                    name, entry_page, entry, entry_type, artists, dates, [d[0] for d in discs], None, ed_lang,
                    repackage_page
                )
        else:
            # Example: https://kpop.fandom.com/wiki/Tuesday_Is_Better_Than_Monday
            yield DiscographyEntryEdition(
                name, entry_page, entry, entry_type, artists, dates, None, None, find_language(entry_page, None, langs),
                repackage_page
            )

    @classmethod
    def process_edition_parts(cls, edition: 'DiscographyEntryEdition') -> Iterator['DiscographyEntryPart']:
        tracks = edition._content
        if tracks.__class__ is CompoundNode and isinstance(tracks[0], ListNode):
            if len(tracks) != 1:
                log.debug(f'Warning: tracks node on {edition.page} may contain additional data - len={len(tracks)}')
            tracks = tracks[0]

        if isinstance(tracks, ListNode):
            yield DiscographyEntryPart(None, edition, tracks)
        elif isinstance(tracks, list):
            for i, track_node in enumerate(tracks):
                yield DiscographyEntryPart(f'CD{i + 1}', edition, track_node)
        elif tracks is None:
            if edition.type == DiscoEntryType.Single:
                yield DiscographyEntryPart(None, edition, None)
            else:
                log.warning(f'Unexpected type={edition.type} for {edition!r}')
        else:
            try:
                # noinspection PyUnresolvedReferences
                log.warning(f'Unexpected type for {edition!r}._content: {tracks.pformat()}', extra={'color': 'red'})
            except AttributeError:
                log.warning(f'Unexpected type for {edition!r}._content: {tracks!r}')

    @classmethod
    def parse_track_name(cls, node: N) -> Name:
        if isinstance(node, String):
            # log.debug(f'Processing track name from String {node=}')
            return _process_track_string(node.value)
        elif node.__class__ is CompoundNode:
            if has_item_types(node, String, Tag) and is_node_with(node[1], Tag, String, name='small'):
                # log.debug(f'Processing track name with small tag from {node=}')
                return _process_track_string(node[0].value, node[1].value.value)
            elif has_item_types(node, String, Link, String) and node[0].value == '"':
                # log.debug(f'Processing track name with String+Link+String from {node=}')
                return _process_track_string(f'"{node[1].show}{node[2].value}')
            elif node.only_basic and not node.find_one(Link, recurse=True):
                # log.debug(f'Processing track name with basic compound and no links from {node=}')
                return _process_track_string(' '.join(str(n.show if isinstance(n, Link) else n.value) for n in node))
            else:
                # log.debug(f'Processing track name with complex content from {node=}')
                return _process_track_complex(node)
        else:
            log.warning(f'parse_track_name has no handling yet for: {node}', extra={'color': 9})

    @classmethod
    def parse_single_page_track_name(cls, page: WikiPage) -> Name:
        name = cls._album_page_name(page)
        if not isinstance(name, Name):
            name = Name.from_enclosed(name)

        infobox = page.infobox
        try:
            length = infobox['length'].value
        except KeyError:
            pass
        else:
            name.update(extra={'length': length})
        try:
            artist = infobox['artist']
        except KeyError:
            pass
        else:
            if isinstance(artist, CompoundNode):
                extra, remainder, artists = _process_track_extra_nodes(artist.children, 'artists', page)
                if extra:
                    name.update_extra(extra)

        return name

    @classmethod
    def parse_group_members(cls, artist_page: WikiPage) -> Dict[str, List[str]]:
        try:
            members_section = artist_page.sections.find('Members')
        except (KeyError, AttributeError):
            log.debug(f'Members section not found for {artist_page}')
            return {}

        if (
            type(members_section.content) is CompoundNode
            and (tables := list(members_section.find_all(Table)))
            and len(tables) == 1  # noqa
        ):
            log.debug(f'Members section {members_section} => {tables[0]}')
            members_node = tables[0]
        else:
            members_node = members_section.content

        members = {'current': []}
        section = 'current'
        if isinstance(members_node, Table):
            for row in members_node:
                # noinspection PyUnboundLocalVariable
                if (
                    isinstance(row, MappingNode)
                    and (name := row.get('Name'))
                    and (title := get_artist_title(name, artist_page))
                ):
                    # noinspection PyUnboundLocalVariable
                    members[section].append(title)
                elif isinstance(row, TableSeparator) and row.value and isinstance(row.value, String):
                    section = row.value.value
                    members[section] = []
        else:
            for member in members_node.iter_flat():
                if title := get_artist_title(member, artist_page):
                    members['current'].append(title)

        if sub_units := artist_page.sections.find('Sub-units', None):
            members['sub_units'] = []
            for sub_unit in sub_units.content.iter_flat():
                if title := get_artist_title(sub_unit, artist_page):
                    members['sub_units'].append(title)

        return members

    @classmethod
    def parse_member_of(cls, artist_page: WikiPage) -> Iterator[Link]:
        if intro := artist_page.intro():
            log.debug(f'Looking for groups in intro for {artist_page}', extra={'color': 11})
            try:
                links = intro.find_all(Link, recurse=True)
            except AttributeError:
                log.debug(f'Error finding links on page={artist_page!r} in {intro=}')
            else:
                for link, entity in EntertainmentEntity.from_links(links, strict=0).items():
                    if entity._categories == GROUP_CATEGORIES:
                        log.debug(f'Found link from {artist_page} to group={entity}', extra={'color': 11})
                    if entity._categories == GROUP_CATEGORIES and (members := entity.members):  # noqa
                        log.debug(
                            f'Found link from {artist_page} to group={entity} with {members=}', extra={'color': 11}
                        )
                        if any(artist_page == page for m in members for page in m.pages):
                            yield link

    @classmethod
    def parse_disco_page_entries(cls, disco_page: WikiPage, finder: 'DiscographyEntryFinder') -> None:
        # This site does not use discography pages.
        return None

    @classmethod
    def parse_soundtrack_links(cls, page: WikiPage) -> Iterator[Link]:
        try:
            links_section = page.sections.find('Discography')
        except (KeyError, AttributeError):
            log.debug(f'Discography section not found for {page}')
            return

        yield from links_section.find_all(Link, True)

    @classmethod
    def parse_source_show(cls, page: WikiPage) -> Optional[TVSeries]:
        raise NotImplementedError


# noinspection PyAbstractClass
class KindieFandomParser(KpopFandomParser, site='kindie.fandom.com'):
    pass


def is_node_with(obj: AnyNode, cls: NodeTypes, val_cls: NodeTypes, **kwargs):
    if not isinstance(obj, cls):
        return False
    if not isinstance(obj.value, val_cls):
        return False
    if kwargs:
        return all(getattr(obj, k).lower() == v for k, v in kwargs.items())
    return True


def has_item_types(node, *types):
    if len(node) != len(types):
        return False
    return all(isinstance(item, cls) for item, cls in zip(node, types))


def _process_track_complex(orig_node: CompoundNode) -> Name:
    nodes = list(orig_node)
    node = nodes.pop(0)
    remainder = None
    if isinstance(node, String):
        if node.value == '"':
            node = nodes.pop(0)
            if isinstance(node, Link):
                base_name = node.show
                node = nodes.pop(0)
                if isinstance(node, String):
                    remainder = node.value
                    if remainder.count('"') == 1:
                        name_part, remainder = map(str.strip, remainder.split('"', 1))
                        # log.debug(f'{base_name=!r} {name_part=!r} {remainder=!r}')
                        base_name = f'{base_name} {name_part}'
                    # else:
                    #     log.debug(f'{base_name=!r} {remainder=!r}')
                else:
                    raise TypeError(f'Unexpected third node type for track={orig_node!r} {node=!r}')
            else:
                raise ValueError(f'Unexpected second node value for track={orig_node!r} {node=!r}')
        else:
            value = node.value
            # noinspection PyUnresolvedReferences
            if len(nodes) > 1 and value.startswith('"') and has_unpaired(value) and isinstance(nodes[1], String)\
                    and '"' in nodes[1].value and has_unpaired(nodes[1].value):
                value = value[1:]
                # noinspection PyUnresolvedReferences
                nodes[1].value = nodes[1].value.replace('"', '')
            else:
                log.debug(f'{nodes=}')
            split_name = split_enclosed(value, maxsplit=1)
            # log.debug(f'split_enclosed({value!r}) => {split_name}')
            if len(split_name) == 1:
                base_name = split_name[0]
            else:
                base_name, remainder = split_name
                if prefix := next((k for k in REMAINDER_ARTIST_EXTRA_TYPE_MAP if k in remainder and k != '('), None):
                    # log.debug(f'Found {prefix=!r}')
                    if not remainder.startswith(prefix):
                        non_eng, extra_prefix, after = map(str.strip, remainder.partition(prefix))
                        base_name = f'{base_name} {non_eng}'
                        remainder = f'{extra_prefix} {after}'.strip()
    elif isinstance(node, Link):
        split_name = split_enclosed(node.show, maxsplit=1)
        # log.debug(f'split_enclosed({value!r}) => {split_name}')
        if len(split_name) == 1:
            base_name = split_name[0]
        else:
            base_name, remainder = split_name
    else:
        raise TypeError(f'Unexpected first node type for track={orig_node!r} {node=!r}')

    # log.debug(f'Processing complex track node: {base_name=!r} {remainder=!r} {nodes=}')
    if not remainder and nodes:
        node = nodes.pop(0)
        if is_node_with(node, (Tag, Template), (CompoundNode, String), name='small'):
            # noinspection PyUnresolvedReferences
            if isinstance(node.value, String):
                # noinspection PyUnresolvedReferences
                node = node.value
            else:
                # noinspection PyUnresolvedReferences
                nodes = list(node.value) + nodes
                node = nodes.pop(0)
            if isinstance(node, String):
                remainder = node.value
            else:
                raise TypeError(f'Unexpected tag value node type for track={orig_node!r} {node=!r}')
        elif isinstance(node, String):
            remainder = node.value
        elif isinstance(node, Link):
            if m := UNCLOSED_PAREN_MATCH(base_name):
                base_name, remainder = map(str.strip, m.groups())
                nodes.insert(0, node)
            else:
                raise TypeError(f'Unexpected node type after track name for track={orig_node!r} {node=!r}')
        else:
            raise TypeError(f'Unexpected node type after track name for track={orig_node!r} {node=!r}')

    extra = {}
    if remainder:
        if extra_type := REMAINDER_ARTIST_EXTRA_TYPE_MAP.get(remainder.lower()):
            # log.debug(f'Found {remainder=!r} => {extra_type=!r}')
            extra, remainder, artists = _process_track_extra_nodes(nodes, extra_type, orig_node)
            # log.debug(f'Found {artists=} {remainder=!r} {nodes=} {extra=}')

    remainder = remainder or ''
    if nodes:
        remainder_parts = [remainder]
        for node in nodes:
            if is_node_with(node, Template, MappingNode, name='small'):
                # noinspection PyUnresolvedReferences
                node = node.value['1']
            remainder_parts.append(str(node.show if isinstance(node, Link) else node.value))
        remainder = ' '.join(remainder_parts)

    # log.debug(f'Checking {remainder=!r} for a duration...')
    if m := DURATION_MATCH(remainder):
        before, extra['length'], after = map(str.strip, m.groups())
        for part in (before, after):
            if part:
                extra.update(_process_track_extras(part))

    # log.debug(f'orig_node={orig_node.pformat()} => {base_name=!r} + {extra=!r}')
    name = Name.from_enclosed(base_name, extra=extra or None)
    # log.info(f'parse_track_name has no handling yet for: {node.pformat()}', extra={'color': 10})
    return name


def _process_track_extra_nodes(nodes: List[N], extra_type: str, source: Union[WikiPage, N]):
    root = source if isinstance(source, WikiPage) else source.root
    extra = {}
    artists = []
    remainder = None
    while nodes:
        node = nodes.pop(0)
        # log.debug(f'Processing {node=!r}')
        if isinstance(node, Link):
            artists.append(node)
        elif isinstance(node, String):
            if start_str := next((val for val in (')', 'duet)', 'solo)') if node.value.startswith(val)), None):
                if len(artists) == 1:
                    extra[extra_type] = artists[0]
                else:
                    extra[extra_type] = CompoundNode.from_nodes(artists, root=root, delim=' ')
                remainder = node.value[len(start_str):].strip()
                break
            elif node.value.startswith('feat.') and node.value.endswith(')'):
                if len(artists) == 1:
                    extra[extra_type] = artists[0]
                else:
                    extra[extra_type] = CompoundNode.from_nodes(artists, root=root, delim=' ')
                extra['feat'] = node.value[5:-1].strip()
                break
            elif m := VERSION_SEARCH(node.value):
                # log.debug(f'Found version match={m}')
                version_parts = [m.group(1)]
                if artists and not extra:
                    version_parts = [a.show for a in artists] + version_parts
                    artists = []
                extra['version'] = ' '.join(version_parts)
            elif node.value == '(feat.' and nodes:
                feat = []
                while nodes:
                    _node = nodes.pop(0)
                    if isinstance(_node, String) and ')' in _node.value:
                        before, _, after = map(str.strip, _node.value.partition(')'))
                        if before:
                            feat.append(String(before, root=root))
                        if after:
                            nodes.insert(0, String(after, root=root))
                        break
                    else:
                        feat.append(_node)

                if feat:
                    if len(feat) == 1:
                        extra['feat'] = feat[0]
                    else:
                        extra['feat'] = CompoundNode.from_nodes(feat, root=root, delim=' ')
            else:
                # log.debug(f'Assuming {node=!r} is part of artists')
                artists.append(node)
        elif is_node_with(node, Template, CompoundNode) and node.value.__class__ is CompoundNode:
            _nodes = node.value.children.copy()
            _nodes.extend(nodes)
            nodes = _nodes
        else:
            raise TypeError(f'Unexpected artist node type for track={source!r} {node=!r}')

    return extra, remainder, artists


def _process_track_string(text: str, extra_content: Optional[str] = None) -> Name:
    # log.debug(f'Processing track str={text!r} with {extra_content=!r}')
    extra = {}
    if extra_content:
        extra.update(_process_track_extras(extra_content))
    if m := DURATION_MATCH(text):
        text, extra['length'], after = map(str.strip, m.groups())
        if after:
            extra.update(_process_track_extras(after))

    if text.startswith('"') and not text.endswith('"') and text.count('"') == 1:
        text += '"'

    parts = split_enclosed(text)
    if (part_count := len(parts)) == 1:
        parts = split_enclosed(parts[0])
    elif part_count > 1 and text.startswith('"'):
        for part in parts[1:]:
            extra.update(_process_track_extras(part))
        parts = split_enclosed(parts[0])

    # log.debug(f'{parts=}')
    tmp_parts = []
    non_eng = []
    for part in parts:
        extra_type, part = _classify_track_part(part)
        if extra_type:
            if extra_type == 'version' and (current := extra.get(extra_type)):
                # noinspection PyUnboundLocalVariable
                if isinstance(current, list):
                    # noinspection PyUnboundLocalVariable
                    current.append(part)
                else:
                    # noinspection PyUnboundLocalVariable
                    extra[extra_type] = [current, part]
            else:
                extra[extra_type] = part
        else:
            if LangCat.contains_any(part, LangCat.non_eng_cats):
                non_eng.append(part)
            else:
                tmp_parts.append(part)

    name = Name(non_eng=combine_with_parens(non_eng) if non_eng else None, extra=extra or None)
    if tmp_parts:
        if (part_count := len(tmp_parts)) == 1:
            name.update(_english=tmp_parts[0])
        elif part_count > 1:
            name_parts = []
            for part in tmp_parts:
                if name.has_romanization(part):
                    name.update(romanized=part)
                else:
                    name_parts.append(part)
            if name_parts:
                name.update(_english=combine_with_parens(name_parts))
    return name


def _classify_track_part(text: str) -> Tuple[Optional[str], Union[str, bool]]:
    text = text.replace(' : ', ': ')
    lc_text = text.lower()
    if lc_text.startswith(('inst.', 'instrumental')):
        return 'instrumental', True
    elif lc_text.startswith('acoustic'):
        if lc_text.endswith(('version', 'ver.')) and not lc_text[8:].strip().startswith('ver'):
            return 'version', text
        return 'acoustic', True
    elif lc_text.endswith(('version', 'ver.')):
        return 'version', text
    elif lc_text.endswith(' ost'):
        return 'album', text
    elif lc_text.startswith(('feat.', 'featuring')):
        return 'feat', text.split(maxsplit=1)[1]
    elif lc_text.endswith('remix'):
        return 'remix', text
    elif lc_text == 'extended play':
        return 'misc', text
    elif lc_text.endswith('only'):
        return 'availability', text
    else:
        return None, text


def _process_track_extras(text: str) -> Iterator[Tuple[str, Any]]:
    for part in split_enclosed(text):
        extra_type, part = _classify_track_part(part)
        yield extra_type or 'misc', part


def _process_album_version(title: str):
    if ends_with_enclosed(title):
        _name, _ver = split_enclosed(title, reverse=True, maxsplit=1)
        lc_ver = _ver.lower()
        if 'ver' in lc_ver:
            if lang := LANG_ABBREV_MAP.get(lc_ver.split(maxsplit=1)[0]):
                return _name, lang
    else:
        lc_title = title.lower()
        if 'ver' in lc_title:
            if lang := LANG_ABBREV_MAP.get(lc_title.split(maxsplit=1)[0]):
                return None, lang

    return title, None


def _find_page_languages(entry_page: WikiPage) -> Set[str]:
    langs = set()
    for cat in entry_page.categories:
        if cat.endswith('releases'):
            for word in cat.split():
                if lang := LANG_ABBREV_MAP.get(word):
                    langs.add(lang)
                    break
    return langs


def _find_release_dates(infobox: Template) -> List[date]:
    dates = []
    if released := infobox.value.get('released'):
        for dt_str in RELEASE_DATE_FINDITER(released.raw.string):
            dates.append(parse_date(dt_str.group(1)))
    return dates


def _find_artist_links(infobox: Template, entry_page: WikiPage) -> Set[Link]:
    try:
        all_links = {link.title: link for link in entry_page.find_all(Link)}
    except Exception as e:
        raise RuntimeError(f'Error finding artist links for {entry_page=}') from e
    artist_links = set()
    if artists := infobox.value.get('artist'):
        if isinstance(artists, String):
            artists_str = artists.value
            if artists_str.lower() not in ('various', 'various artists'):
                for artist in artists_str.split(', '):
                    artist = artist.strip()
                    if artist.startswith('& '):
                        artist = artist[1:].strip()
                    if artist_link := all_links.get(artist):
                        artist_links.add(artist_link)
        elif isinstance(artists, Link):
            artist_links.add(artists)
        elif isinstance(artists, CompoundNode):
            for artist in artists:
                if isinstance(artist, Link):
                    artist_links.add(artist)
                elif isinstance(artist, String):
                    if artist_link := all_links.get(artist.value):
                        artist_links.add(artist_link)
    return artist_links
