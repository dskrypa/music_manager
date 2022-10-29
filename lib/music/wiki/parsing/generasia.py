"""
:author: Doug Skrypa
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, date
from os.path import commonprefix
from typing import TYPE_CHECKING, Iterator, Optional, Any

from ds_tools.unicode.languages import LangCat
from wiki_nodes.nodes import N, Link, String, CompoundNode, MappingNode, Template, ListEntry, List
from wiki_nodes.nodes.transformers import transform_section
from wiki_nodes.page import WikiPage
from wiki_nodes.utils import strip_style

from music.common.disco_entry import DiscoEntryType
from music.text.extraction import parenthesized, split_enclosed, ends_with_enclosed
from music.text.name import Name
from music.text.spellcheck import is_english
from music.text.utils import find_ordinal
from ..album import DiscographyEntry, DiscographyEntryEdition, DiscographyEntryPart
from ..base import TemplateEntity, EntertainmentEntity, SINGER_CATEGORIES, GROUP_CATEGORIES, TVSeries
from ..disco_entry import DiscoEntry
from .abc import WikiParser, EditionIterator
from .utils import LANG_ABBREV_MAP, PageIntro, get_artist_title, find_language

if TYPE_CHECKING:
    from ..discography import DiscographyEntryFinder
    from ..typing import OptStr, StrDateMap

__all__ = ['GenerasiaParser']
log = logging.getLogger(__name__)

DATE_PAT_MATCH = re.compile(r'^\[\d{4}(?:\.\d{2}\.\d{2})?\]\s*(.*)$').match
OST_PAT_SEARCH = re.compile(r'\sOST(?:\s*|$)').search

MEMBER_TYPE_SECTIONS = {'former': 'Former Members', 'hiatus': 'Hiatus', 'sub_units': 'Sub-Units'}
RELEASE_CATEGORY_LANGS = {'k-': 'Korean', 'j-': 'Japanese', 'mandopop': 'Mandarin'}

# TODO:
"""
The bit in parentheses at the end is wrong:
https://www.generasia.com/wiki/Map_of_the_Soul:_7
[DRY RUN] Would update <SongFile('new_sorting/kpop_2020-02-22/bts/BTS-MOTS7-320-K2N/02. 작은 것들을 위한 시 (Boy With Luv) (Feat. Halsey).mp3')> by changing...
  - artist from                                  '방탄소년단 (BTS)' to 'BTS (방탄소년단) (feat. Halsey ) (작은 것들을 위한 시))'
"""


class GenerasiaParser(WikiParser, site='www.generasia.com'):
    __slots__ = ()

    def parse_artist_name(self, artist_page: WikiPage) -> Iterator[Name]:
        yield from PageIntro(artist_page).names()
        try:
            section = artist_page.sections.find('Profile')
        except KeyError:
            pass
        else:
            profile_content = section.content
            if isinstance(profile_content, List):
                try:
                    profile = profile_content.as_mapping(multiline=False)
                except Exception as e:
                    log.debug(f'Error processing profile on {artist_page}: {e}')
                    return
            elif isinstance(profile_content, CompoundNode) and isinstance(profile_content[0], List):
                try:
                    profile = profile_content[0].as_mapping(multiline=False)
                except Exception as e:
                    log.debug(f'Error processing profile on {artist_page}: {e}')
                    return
            else:
                log.debug(f'Unexpected {profile_content=!r} on {artist_page}')
                return

            for key in ('Stage Name', 'Real Name', 'Korean Name'):
                try:
                    value = profile[key]
                    if isinstance(value, CompoundNode):
                        value = value[0]
                    if isinstance(value, String):
                        value = value.value
                    else:
                        raise ValueError(f'Unexpected {value=}')
                except KeyError:
                    pass
                except Exception:
                    log.error(f'Error processing profile from {artist_page}:\n{profile.pformat()}', extra={'color': 9})
                    raise
                else:
                    yield Name.from_enclosed(value)

    def parse_album_name(self, node: N) -> Name:
        # log.debug(f'Processing node: {node}')
        _node = node
        if not isinstance(node, list) and type(node) is not CompoundNode:
            nodes = iter([node])
        else:
            nodes = iter(node)

        node = next(nodes)
        if isinstance(node, String) and DATE_PAT_MATCH(node.value):
            node = next(nodes)

        if isinstance(node, Link):
            title = node.show
        elif isinstance(node, String):
            title = node.value
        else:
            raise TypeError(f'Unexpected node type following date: {node}')

        artists = None
        node = next(nodes, None)
        if node and isinstance(node, String):
            node_str = node.value
            if node_str == '-' or node_str.startswith('&') and node_str.endswith('-'):
                # [date] [[primary artist]] - [[{romanized} (eng)]] (han; lit)
                # primary_artist = title
                node = next(nodes, None)
                if isinstance(node, Link):
                    title = node.show
                else:
                    raise TypeError(f'Unexpected node type following date: {node}')
                node = next(nodes, None)
            elif node_str == '(':
                node = next(nodes, None)
                if isinstance(node, Link):
                    try:
                        entity = EntertainmentEntity.from_link(node)
                    except Exception as e:
                        log.debug(f'Error retrieving EntertainmentEntity from {node}: {e}')
                    else:
                        if entity._categories in (GROUP_CATEGORIES, SINGER_CATEGORIES):
                            artists = [String(node_str), node]
                            while node := next(nodes, None):
                                artists.append(node)
                                if isinstance(node, String) and node.value.endswith(')'):
                                    break
                            node = next(nodes, None)

        title, non_eng, lit_translation, extras, incomplete_extra = _split_name_parts(title, node)
        # log.debug(f'{title=!r} {non_eng=!r} {lit_translation=!r} {extras=} {incomplete_extra=!r}')
        if artists:
            extras['artists'] = CompoundNode.from_nodes(artists, delim=' ')

        if incomplete_extra:
            recombined = process_incomplete_extra(extras, incomplete_extra, nodes)
            if non_eng is None and lit_translation is None:
                if recombined.__class__ is CompoundNode and isinstance(recombined[-1], String):
                    last_val = recombined[-1].value                                 # type: str
                    if last_val.startswith(')') and String('(') in recombined:
                        recombined[-1] = String(')')
                        extras[incomplete_extra] = CompoundNode.from_nodes(recombined.children, delim=' ')
                        last_val = last_val[1:].strip()
                        if last_val.startswith(')'):
                            last_val = last_val[1:].strip()
                        non_eng, lit_translation = _split_non_eng_lit(last_val)
            incomplete_extra = None

        # log.debug(f'{title=!r} {non_eng=!r} {lit_translation=!r} {extras=} {incomplete_extra=!r}')

        if not title.endswith(')') and ')' in title:
            pos = title.rindex(')') + 1
            incomplete_extra = process_extra(extras, title[pos:].strip())
            title = title[:pos].strip()

        if '(' in title and ')' not in title:
            title += ')'

        # [date] [[{romanized} (eng)]] (han; lit)
        #        ^_______title_______^
        name = Name(non_eng=non_eng, lit_translation=lit_translation)
        if opener_closer := ends_with_enclosed(title, exclude='"'):
            opener, closer = opener_closer
            if non_eng:
                if non_eng.endswith(')') and '(' in non_eng and name.has_romanization(title):
                    name.set_eng_or_rom(title)
                else:
                    a, b = split_enclosed(title, reverse=True, maxsplit=1)
                    if a.endswith(')') and '(' in a:
                        incomplete_extra = process_extra(extras, b)
                        a, b = split_enclosed(a, reverse=True, maxsplit=1)

                    # log.debug(f'Split title -> a={a!r} (eng: {is_english(a)}), b={b!r} (eng: {is_english(b)})')
                    if name.has_romanization(a):
                        # noinspection PyUnresolvedReferences
                        if _node.root and _node.root.title == title:
                            name.set_eng_or_rom(a, value=title)
                            name.non_eng = title.replace(a, non_eng)
                            name.lit_translation = title.replace(a, lit_translation) if lit_translation else None
                        else:
                            name.set_eng_or_rom(a)
                            if is_extra(b):
                                incomplete_extra = process_extra(extras, b)
                            else:
                                name._english = f'{name._english} ({b})' if name._english else b
                    elif name.has_romanization(b):
                        name.set_eng_or_rom(b)
                        if is_extra(a):
                            incomplete_extra = process_extra(extras, a)
                        else:
                            name._english = f'{name._english} ({a})' if name._english else a
                    elif name.non_eng and is_english(b) and not is_english(a):
                        name.romanized = a      # Assume that it is a romanization
                        if is_extra(b):
                            incomplete_extra = process_extra(extras, b)
                        else:
                            name._english = b
                    else:
                        # noinspection PyUnresolvedReferences
                        if _node.root and _node.root.title == title:
                            name._english = title
                        else:
                            if is_extra(b):
                                name._english = a
                                incomplete_extra = process_extra(extras, b)
                            else:
                                name._english = f'{a} ({b})'
            elif title.startswith(opener) and title.endswith(closer) and no_extra_enclosers(title, opener_closer):
                name.set_eng_or_rom(title)
            else:
                try:
                    a, b = split_enclosed(title, reverse=True, maxsplit=1)
                except Exception:
                    log.error(f'Error splitting {title=!r}', exc_info=True)
                    raise

                if OST_PAT_SEARCH(b) or is_extra(b):
                    eng_title = a
                    incomplete_extra = process_extra(extras, b)
                else:
                    eng_title = title

                name.set_eng_or_rom(eng_title, 0.5)
        else:
            if non_eng and name.has_romanization(title):
                if is_english(title):
                    name._english = title
                else:
                    name.romanized = title
                    if lit_translation and ' / ' in lit_translation:
                        lit, eng = lit_translation.split(' / ', 1)
                        if f'{lit} / {eng}' not in _node.raw.string:  # Make sure it had formatting after lit / before eng
                            name.update(_english=eng, lit_translation=lit)
            else:
                name._english = title

        if incomplete_extra:
            process_incomplete_extra(extras, incomplete_extra, nodes)
        if extras:
            name.extra = extras
        return name

    parse_track_name = parse_album_name

    def parse_single_page_track_name(self, page: WikiPage) -> Name:
        raise NotImplementedError

    def process_disco_sections(self, artist_page: WikiPage, finder: DiscographyEntryFinder):
        for section_prefix in ('', 'Korean ', 'Japanese ', 'International '):
            try:
                section = artist_page.sections.find(f'{section_prefix}Discography')
            except KeyError:
                continue
            lang = section_prefix.strip() if section_prefix in ('Korean ', 'Japanese ') else None
            for alb_type, alb_type_section in section.children.items():
                lc_alb_type = alb_type.lower()
                if any(val in lc_alb_type for val in ('video', 'dvd', 'vinyls')) or lc_alb_type == 'other':
                    continue
                de_type = DiscoEntryType.for_name(alb_type)
                content = alb_type_section.content
                if not isinstance(content, List):
                    log.warning(
                        f'Unexpected {section_prefix} album section content type={type(content)} on {artist_page=}',
                        stack_info=True,
                    )
                    continue
                for entry in content.iter_flat():
                    try:
                        self._process_disco_entry(artist_page, finder, de_type, entry, lang)
                    except InvalidEntry as e:
                        log.debug(e)
                    except Exception:
                        log.error(
                            f'Unexpected error processing {section=} {entry=} on {artist_page=}:',
                            extra={'color': 9}, exc_info=True
                        )

    def _process_disco_entry(
        self,
        artist_page: WikiPage,
        finder: DiscographyEntryFinder,
        de_type: DiscoEntryType,
        entry: CompoundNode,
        lang: Optional[str],
    ):
        name = self.parse_album_name(entry)
        log.log(9, f'Processing {name!r}')
        entry_type = de_type  # Except for collabs with a different primary artist
        if isinstance(entry, String):
            raise InvalidEntry(f'Unexpected {entry=} on {artist_page=}')
        else:
            entry_link = next(entry.find_all(Link, True), None)  # Almost always the 1st link
        song_title = entry_link.show if entry_link else None

        """
        [YYYY.MM.DD] {Album title: romanized OR english} [(repackage)]
        [YYYY.MM.DD] {Album title: romanized (english)} [(hangul)]
        [YYYY.MM.DD] {Album title: romanized OR english} [(hangul[; translation])]
        [YYYY.MM.DD] {Album title: romanized OR english} [(hangul[; translation])] (collaborators)
        [YYYY.MM.DD] {Album title: romanized OR english} [(hangul[; translation])] (primary artist feat. collaborators)
        [YYYY.MM.DD] {Album title: romanized OR english} [(hangul[; translation])] (feat. collaborators)
        [YYYY.MM.DD] {primary artist} - {Album title: romanized OR english} (#track_num track title (feat. collaborators))
        [YYYY.MM.DD] {primary artist} - {Album title: romanized OR english} (#track_num track title feat. collaborators)
        """

        parts = len(entry)
        if parts == 2:
            # [date] title
            pass
        elif parts >= 3:
            if isinstance(entry[2], String):
                entry_2 = entry[2].value
                if self._check_type(entry, 3, Link) and de_type == DiscoEntryType.Collaboration:
                    if entry_2 == '-':
                        # 1st link = primary artist, 2nd link = disco entry
                        entry_type = DiscoEntryType.Feature
                        entry_link = entry[3]
                        if self._check_type(entry, 4, String) and not entry[4].lower.startswith('(feat'):
                            # [date] primary - album (song (feat artists))
                            song_title = entry[4].value[1:].partition('(')[0]
                    elif entry_2 == '(' and self._check_type(entry, 4, String) and entry[4].lower.startswith('feat'):
                        # [date] single (primary feat collaborators)
                        pass

        first_str = entry[0].value
        date_str = first_str[1:first_str.index(']')]
        if len(date_str) == 4:
            date_obj = date(int(date_str), 1, 1)
        else:
            date_obj = datetime.strptime(date_str, '%Y.%m.%d').date()

        # noinspection PyTypeChecker
        disco_entry = DiscoEntry(
            artist_page, entry, type_=entry_type, lang=lang, date=date_obj, link=entry_link, song=song_title, title=name
        )
        if entry_link:
            finder.add_entry_link(entry_link, disco_entry)
        else:
            if isinstance(entry[1], String):
                disco_entry.title = entry[1].value
            finder.add_entry(disco_entry, entry)

    def process_album_editions(self, entry: DiscographyEntry, entry_page: WikiPage) -> EditionIterator:
        processed = transform_section(entry_page.sections)[1]
        langs = set()
        for cat in entry_page.categories:
            if cat.endswith('(releases)'):
                for prefix, lang in RELEASE_CATEGORY_LANGS.items():
                    if cat.startswith(prefix):
                        langs.add(lang)
                        break
                else:
                    log.debug(f'Unrecognized release category: {cat!r} on {entry_page}')

        repackage = False
        for node in processed:
            if isinstance(node, MappingNode) and 'Artist' in node:
                try:
                    yield from EditionProcessor(entry, entry_page, node, langs, repackage)
                except Exception as e:
                    log.debug(f'Error processing edition on {entry_page=}: {e}', extra={'color': 9})
                    # log.debug(f'Error processing edition on {entry_page=} node={node.pformat()}', exc_info=True, extra={'color': 9})
                else:
                    repackage = True

    def process_edition_parts(self, edition: DiscographyEntryEdition) -> Iterator[DiscographyEntryPart]:
        if (tracks := edition._content) and tracks[0].children:
            for node in tracks:
                yield DiscographyEntryPart(node.value.value, edition, node.sub_list)
        else:
            yield DiscographyEntryPart(None, edition, edition._content)

    def parse_album_number(self, entry_page: WikiPage) -> Optional[int]:
        root = transform_section(entry_page.sections)[0]  # Necessary to populate the Information section
        try:
            info = root['Information'].content
        except KeyError:
            log.debug(f'No Information section found on {entry_page}')
            return None
        else:
            return find_ordinal(info.raw.string)

    def parse_group_members(self, artist_page: WikiPage) -> dict[str, list[str]]:
        try:
            members_section = artist_page.sections.find('Members')
        except (KeyError, AttributeError):
            log.debug(f'Members section not found for {artist_page}')
            return {}

        members = {'current': []}
        for member in members_section.content.iter_flat():
            if title := get_artist_title(member, artist_page):
                members['current'].append(title)

        for key, section_name in MEMBER_TYPE_SECTIONS.items():
            if section_members := members_section.find(section_name, None):
                members[key] = []
                for member in section_members.content.iter_flat():
                    if title := get_artist_title(member, artist_page):
                        members[key].append(title)

        return members

    def parse_member_of(self, artist_page: WikiPage) -> Iterator[Link]:
        if external_links := artist_page.sections.find('External Links', None):
            if isinstance(external_links.content, CompoundNode):
                for node in external_links.content:
                    if isinstance(node, Template):
                        tmpl = TemplateEntity.from_name(node.name, artist_page.site)
                        if tmpl.group:
                            yield next(iter(tmpl.group.pages)).as_link
        """
        links = []
        member_str_index = None
        for i, node in enumerate(page.intro()):
            if isinstance(node, String) and 'is a member of' in node.value:
                member_str_index = i
            elif member_str_index is not None:
                if isinstance(node, Link):
                    yield node
                if i - member_str_index > 3:
                    break
        """

    def parse_disco_page_entries(self, disco_page: WikiPage, finder: DiscographyEntryFinder) -> None:
        # This site does not use discography pages.
        return None

    def parse_soundtrack_links(self, page: WikiPage) -> Iterator[Link]:
        raise NotImplementedError

    def parse_source_show(self, page: WikiPage) -> Optional[TVSeries]:
        raise NotImplementedError


class EditionProcessor:
    __slots__ = ('entry', 'entry_page', 'node', 'langs', 'repackage')
    entry: DiscographyEntry
    entry_page: WikiPage
    node: MappingNode
    langs: set[str]
    repackage: bool

    def __init__(
        self, entry: DiscographyEntry, entry_page: WikiPage, node: MappingNode, langs: set[str], repackage: bool = False
    ):
        self.entry = entry
        self.entry_page = entry_page
        self.node = node
        self.langs = langs
        self.repackage = repackage

    def __iter__(self) -> EditionIterator:
        yield from self.editions()

    def editions(self) -> EditionIterator:
        name_key = list(self.node.keys())[1]  # Works because of insertion order being maintained
        entry_type = DiscoEntryType.for_name(name_key)
        artist_link = self.node['Artist'].value
        album_name = self.get_album_name(name_key)

        log.log(9, f'Processing edition entry with {album_name=!r} {entry_type=!r} {artist_link=!r}')
        lang, version, edition = self.get_name_info(album_name)
        release_dates = self.get_release_dates()
        for key, value in self.node.items():
            # Traverse the dl of Artist/Album/Tracklist/etc; may have multiple Tracklist entries for editions
            # `value` is the List node containing track info
            lc_key = key.lower().strip()
            if 'tracklist' not in lc_key or lc_key.startswith('dvd '):
                continue

            _edition = edition
            if lc_key != 'tracklist':
                tl_edition = strip_style(key.rsplit(maxsplit=1)[0]).strip('"')
                if tl_edition.lower() == 'cd':
                    tl_edition = None
                if tl_edition:
                    _edition = f'{edition} - {tl_edition}' if edition else tl_edition

            yield DiscographyEntryEdition(
                album_name,
                self.entry_page,
                self.entry,
                entry_type,
                artist_link,
                release_dates,
                value,
                _edition or version,
                find_language(value, lang, self.langs),
                self.repackage,
            )

    def get_album_name(self, name_key: str) -> str:
        album_name_node = self.node[name_key].value
        if isinstance(album_name_node, String):
            return album_name_node.value
        elif album_name_node is not None:
            album_name = album_name_node[0].value
            if isinstance(album_name, String):
                album_name = album_name.value
            if album_name.endswith('('):
                album_name = album_name[:-1].strip()
            return album_name

        album_name_node = self.node[name_key]
        if isinstance(album_name_node, ListEntry) and album_name_node.children:
            try:
                # Example: https://www.generasia.com/wiki/The_Best_(Girls%27_Generation)
                names = [c.value for c in album_name_node.sub_list.iter_flat()]
            except AttributeError:
                # TODO:
                # https://www.generasia.com/wiki/Miina_(Bonamana)
                # https://www.generasia.com/wiki/The_SHINee_World
                log.error(f'Unexpected value for {album_name_node=!r} on page={self.entry_page}')
            else:
                if prefix := clean_common_prefix(names):
                    log.debug(f'Using album={prefix!r} for {album_name_node} on page={self.entry_page}')
                    return prefix

        raise ValueError(f'Unexpected {album_name_node=}')

    def get_name_info(self, album_name: str) -> tuple[OptStr, OptStr, OptStr]:
        lang, version, edition = None, None, None
        lc_album_name = album_name.lower()
        if ver_ed_indicator := next((val for val in ('ver.', 'edition') if val in lc_album_name), None):
            try:
                album_name, ver_ed_value = split_enclosed(album_name, True, maxsplit=1)
            except ValueError:
                log.debug(f"Found 'ver.' in {album_name=} on page={self.entry_page} but could not split it")
            else:
                if ver_ed_indicator == 'edition':
                    edition = ver_ed_value
                else:
                    version = ver_ed_value
                try:
                    lang = LANG_ABBREV_MAP[ver_ed_value.split(maxsplit=1)[0].lower()]
                except KeyError:
                    pass

        return lang, version, edition

    def get_release_dates(self) -> StrDateMap:
        try:
            release_dates_node = self.node['Released']
        except KeyError:
            for disco_entry in self.entry.disco_entries:
                if disco_entry.date:
                    return {None: disco_entry.date}
            else:
                return {}
        else:
            if release_dates_node.children:
                release_dates = []
                for r_date in release_dates_node.sub_list.iter_flat():
                    r_date_str = r_date.value if isinstance(r_date, String) else r_date[0].value
                    release_dates.append(datetime.strptime(r_date_str, '%Y.%m.%d').date())

                if not release_dates:
                    return {}
                if len(release_dates) > 1:
                    log.debug(f'Using first value after finding multiple {release_dates=}')

                return {None: release_dates[0]}
            else:
                value = release_dates_node.value
                if isinstance(value, CompoundNode):
                    value = value[0]
                value = value.value
                try:
                    return {None: datetime.strptime(value[:10], '%Y.%m.%d').date()}
                except Exception:
                    log.error(f'Error processing dates from {release_dates_node.value!r}', extra={'color': 9})
                    raise


def clean_common_prefix(strs) -> str:
    prefix = commonprefix(strs).strip()     # type: str
    if prefix.endswith(('~', '-', '(')):
        prefix = prefix[:-1]
    return prefix.strip()


def is_extra(text: str) -> bool:
    return bool(classify_extra(text))


def _split_name_parts(
    title: str, node: Optional[N]
) -> tuple[str, Optional[str], Optional[str], dict[str, Any], Optional[str]]:
    """
    :param title: The title
    :param node: The node to split
    :return:
    """
    # log.debug(f'_split_name_parts({title=!r}, {node=!r})')
    original_title = title
    non_eng, lit_translation, name_parts_str, extra = None, None, None, None
    if isinstance(node, String):
        name_parts_str = parenthesized(node.value)
    elif node is None:
        if title.endswith(')'):
            try:
                title, name_parts_str = split_enclosed(title, reverse=True, maxsplit=1)
            except ValueError:
                pass

    # log.debug(f'{title=!r} {name_parts_str=!r}')
    if name_parts_str:
        non_eng, lit_translation = _split_non_eng_lit(name_parts_str)
    if non_eng is None and lit_translation is None:
        if node is None:
            title = original_title
        else:
            extra = name_parts_str

    extras = {}
    incomplete_extra = None
    if extra:
        # log.info(f'{node=!r} => {extra=!r}', extra={'color': 'red'})
        incomplete_extra = process_extra(extras, extra)

    # log.debug(f'node={node!r} => title={title!r} non_eng={non_eng!r} lit={lit_translation!r} extras={extras}')
    return title, non_eng, lit_translation, extras, incomplete_extra


def _split_non_eng_lit(name_parts_str: str):
    # log.debug(f'Splitting: {name_parts_str!r}')
    non_eng, lit_translation = None, None
    if name_parts_str.startswith('('):
        name_parts_str = parenthesized(name_parts_str)
    if name_parts_str and LangCat.contains_any(name_parts_str, LangCat.asian_cats):
        name_parts = tuple(map(str.strip, name_parts_str.split(';')))
        if len(name_parts) == 1:
            non_eng = name_parts[0]
        elif len(name_parts) == 2:
            non_eng, lit_translation = name_parts
        else:
            raise ValueError(f'Unexpected name parts format: {name_parts_str!r}')
    return non_eng, lit_translation


def process_incomplete_extra(extras: dict, incomplete_extra_type: str, node_iter: Iterator[N]) -> CompoundNode:
    nodes = []
    for node in node_iter:
        if isinstance(node, String):
            value = node.value
            if value == ')':
                break
            elif value.endswith(')'):
                nodes.append(node)
                break
        nodes.append(node)

    if len(nodes) == 1:
        recombined = nodes[0]
    else:
        recombined = CompoundNode.from_nodes(nodes, delim=' ')

    extras[incomplete_extra_type] = recombined
    return recombined


def process_extra(extras: dict, extra: str) -> Optional[str]:
    """
    :param extras: The dict of extras in which the provided extra should be stored
    :param extra: The extra text to be processed
    :return: None if the provided extra was complete, or the type of the incomplete extra if it was not
    """
    if extra.startswith('(') and ')' not in extra:
        extra = extra[1:].strip()
    if extra.startswith('- '):
        extra = extra[1:].strip()
    extra_type = classify_extra(extra)
    if extra_type == 'track':
        if ',' in extra and extra.count('#') > 1:
            extra_type = 'tracks'
            extra = tuple(map(str.strip, extra.split(',')))
        elif ' / ' in extra:
            extra, extras['collabs'] = map(str.strip, extra.split(' / '))
        elif '(' in extra:
            try:
                _extra, collabs = split_enclosed(extra, reverse=True)
            except ValueError:
                pass
            else:
                lc_collabs = collabs.lower()
                if any(val in lc_collabs for val in ('various artists', ' + ', ' & ', ' x ')):
                    extra = _extra
                    extras['collabs'] = collabs
    elif extra_type == 'feat':
        try:
            extra = extra.split(maxsplit=1)[1]
        except IndexError:
            return extra_type

    if extra_type in ('instrumental', 'acoustic'):
        extras[extra_type] = True
    elif extra_type == 'remix' and extra.lower() == 'remix':
        extras[extra_type] = True
    else:
        if extra_type == 'version' and ' RnB ' in extra:
            extra = extra.replace(' RnB ', ' R&B ')
        extras[extra_type] = extra
    return None


def classify_extra(text: str) -> Optional[str]:
    if text.startswith('#'):
        return 'track'
    lc_text = text.lower()
    if lc_text.endswith(' ost'):
        return 'album'
    elif lc_text.endswith('album'):
        return 'album_type'
    elif lc_text.startswith(('feat.', 'featuring')):
        return 'feat'
    elif lc_text.endswith('remix'):
        return 'remix'
    elif lc_text.endswith(('ver.', 'version')):
        return 'version'
    elif lc_text.startswith(('inst.', 'instrumental')):
        return 'instrumental'
    elif lc_text.startswith('acoustic'):
        return 'acoustic'
    elif any(val in lc_text for val in (' ed.', 'edition')):
        return 'edition'

    return None


def no_extra_enclosers(title: str, opener_closer):
    if all(title.count(c) == 1 for c in opener_closer):
        return True
    opener, closer = opener_closer
    if opener == closer:
        return title.count(opener) == 2
    return False


class InvalidEntry(Exception):
    pass
