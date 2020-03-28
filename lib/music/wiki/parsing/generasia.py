"""
:author: Doug Skrypa
"""

import logging
import re
from datetime import datetime
from traceback import format_exc
from typing import TYPE_CHECKING, Iterator, Optional, Set, Tuple, Dict, Any

from ds_tools.unicode.languages import LangCat
from wiki_nodes.nodes import Node, Link, String, CompoundNode, MappingNode
from wiki_nodes.page import WikiPage
from wiki_nodes.utils import strip_style
from ...text.extraction import parenthesized, split_enclosed, ends_with_enclosed
from ...text.name import Name
from ...text.spellcheck import is_english
from ..album import DiscographyEntry, DiscographyEntryEdition
from ..disco_entry import DiscoEntryType, DiscoEntry
from .abc import WikiParser, EditionIterator
from .utils import LANG_ABBREV_MAP

if TYPE_CHECKING:
    from ..discography import DiscographyEntryFinder

__all__ = ['GenerasiaParser']
log = logging.getLogger(__name__)

DATE_PAT_MATCH = re.compile(r'^\[\d{4}\.\d{2}\.\d{2}\]\s*(.*)$').match
OST_PAT_SEARCH = re.compile(r'\sOST(?:\s*|$)').search


class GenerasiaParser(WikiParser, site='www.generasia.com'):
    @classmethod
    def parse_artist_name(cls, artist_page: WikiPage) -> Iterator[Name]:
        # From intro ===========================================================================================
        intro = artist_page.intro
        first_string = intro[0].value if isinstance(intro, CompoundNode) else intro.value
        name = first_string[:first_string.rindex(')') + 1]
        # log.debug(f'Found name: {name}')
        first_part, paren_part = split_enclosed(name, reverse=True, maxsplit=1)
        if '; ' in paren_part:
            yield Name.from_parts((first_part, paren_part.split('; ', 1)[0]))
        else:
            try:
                parts = tuple(map(str.strip, paren_part.split(', and')))
            except Exception:
                yield Name.from_parts((first_part, paren_part))
            else:
                if len(parts) == 1:
                    yield Name.from_parts((first_part, paren_part))
                else:
                    for part in parts:
                        try:
                            part = part[:part.rindex(')') + 1]
                        except ValueError:
                            log.error(f'Error splitting part={part!r}')
                            raise
                        else:
                            part_a, part_b = split_enclosed(part, reverse=True, maxsplit=1)
                            try:
                                romanized, alias = part_b.split(' or ')
                            except ValueError:
                                yield Name.from_parts((first_part, part_a, part_b))
                            else:
                                yield Name.from_parts((first_part, part_a, romanized))
                                yield Name.from_parts((alias, part_a, romanized))

        # From profile =========================================================================================
        try:
            section = artist_page.sections.find('Profile')
        except KeyError:
            pass
        else:
            profile = section.content.as_mapping(multiline=False)
            for key in ('Stage Name', 'Real Name'):
                try:
                    value = profile[key].value
                except KeyError:
                    pass
                else:
                    yield Name.from_enclosed(value)

    @classmethod
    def parse_album_name(cls, node: Node) -> Name:
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

        title, non_eng, lit_translation, extras, incomplete_extra = _split_name_parts(title, node)
        # log.debug(f'title={title!r} non_eng={non_eng!r} lit={lit_translation!r} ex={extras} inc={incomplete_extra!r}')

        if not title.endswith(')') and ')' in title:
            pos = title.rindex(')') + 1
            incomplete_extra = process_extra(extras, title[pos:].strip())
            title = title[:pos].strip()

        if '(' in title and ')' not in title:
            title += ')'

        # [date] [[{romanized} (eng)]] (han; lit)
        #        ^_______title_______^
        name = Name(non_eng=non_eng, lit_translation=lit_translation)
        if ends_with_enclosed(title, exclude='"'):
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
                    elif name.non_eng and is_english(b) and not is_english(a):
                        name.romanized = a      # Assume that it is a romanization
                        if is_extra(b):
                            incomplete_extra = process_extra(extras, b)
                        else:
                            name._english = b
                    else:
                        if _node.root and _node.root.title == title:
                            name._english = title
                        else:
                            if is_extra(b):
                                name._english = a
                                incomplete_extra = process_extra(extras, b)
                            else:
                                name._english = f'{a} ({b})'
            else:
                a, b = split_enclosed(title, reverse=True, maxsplit=1)
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

    @classmethod
    def process_disco_sections(cls, artist_page: WikiPage, finder: 'DiscographyEntryFinder'):
        for section_prefix in ('', 'Korean ', 'Japanese ', 'International '):
            try:
                section = artist_page.sections.find(f'{section_prefix}Discography')
            except KeyError:
                continue
            lang = section_prefix.strip() if section_prefix in ('Korean ', 'Japanese ') else None
            for alb_type, alb_type_section in section.children.items():
                if 'video' in alb_type.lower():
                    continue
                de_type = DiscoEntryType.for_name(alb_type)
                content = alb_type_section.content
                for entry in content.iter_flat():
                    try:
                        cls._process_disco_entry(artist_page, finder, de_type, entry, lang)
                    except Exception as e:
                        msg = f'Unexpected error processing section={section} entry={entry}: {format_exc()}'
                        log.error(msg, extra={'color': 'red'})

    @classmethod
    def _process_disco_entry(
            cls, artist_page: WikiPage, finder: 'DiscographyEntryFinder', de_type: DiscoEntryType, entry: CompoundNode,
            lang: Optional[str]
    ):
        log.debug(f'Processing {cls.parse_album_name(entry)!r}')
        entry_type = de_type  # Except for collabs with a different primary artist
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
                if cls._check_type(entry, 3, Link) and de_type == DiscoEntryType.Collaboration:
                    if entry_2 == '-':
                        # 1st link = primary artist, 2nd link = disco entry
                        entry_type = DiscoEntryType.Feature
                        entry_link = entry[3]
                        if cls._check_type(entry, 4, String) and not entry[4].lower.startswith('(feat'):
                            # [date] primary - album (song (feat artists))
                            song_title = entry[4].value[1:].partition('(')[0]
                    elif entry_2 == '(' and cls._check_type(entry, 4, String) and entry[4].lower.startswith('feat'):
                        # [date] single (primary feat collaborators)
                        pass

        first_str = entry[0].value
        date = datetime.strptime(first_str[:first_str.index(']')], '[%Y.%m.%d').date()
        # noinspection PyTypeChecker
        disco_entry = DiscoEntry(
            artist_page, entry, type_=entry_type, lang=lang, date=date, link=entry_link, song=song_title
        )
        if entry_link:
            finder.add_entry_link(cls.client, entry_link, disco_entry)
        else:
            if isinstance(entry[1], String):
                disco_entry.title = entry[1].value
            finder.add_entry(disco_entry, entry)

    @classmethod
    def process_album_editions(cls, entry: 'DiscographyEntry', entry_page: WikiPage) -> EditionIterator:
        processed = entry_page.sections.processed()
        langs = set()
        for cat in entry_page.categories:
            if cat.endswith('(releases)'):
                if cat.startswith('k-'):
                    langs.add('Korean')
                elif cat.startswith('j-'):
                    langs.add('Japanese')
                elif cat.startswith('mandopop'):
                    langs.add('Mandarin')
                else:
                    log.debug(f'Unrecognized release category: {cat!r}')

        for node in processed:
            if isinstance(node, MappingNode) and 'Artist' in node:
                try:
                    yield from cls._process_album_edition(entry, entry_page, node, langs)
                except Exception as e:
                    log.error(f'Error processing edition node={node}: {e}', exc_info=True)

    @classmethod
    def _process_album_edition(cls, entry: 'DiscographyEntry', entry_page: WikiPage, node: MappingNode, langs: set):
        artist_link = node['Artist'].value
        name_key = list(node.keys())[1]  # Works because of insertion order being maintained
        entry_type = DiscoEntryType.for_name(name_key)
        album_name_node = node[name_key].value

        if isinstance(album_name_node, String):
            album_name = album_name_node.value
        else:
            album_name = album_name_node[0].value
            if album_name.endswith('('):
                album_name = album_name[:-1].strip()

        lang, version, edition = None, None, None
        lc_album_name = album_name.lower()
        if ver_ed_indicator := next((val for val in ('ver.', 'edition') if val in lc_album_name), None):
            try:
                album_name, ver_ed_value = split_enclosed(album_name, True, maxsplit=1)
            except ValueError:
                log.debug(f'Found \'ver.\' in album name on {entry_page} but could not split it: {album_name!r}')
            else:
                if ver_ed_indicator == 'edition':
                    edition = ver_ed_value
                else:
                    version = ver_ed_value
                try:
                    lang = LANG_ABBREV_MAP[ver_ed_value.split(maxsplit=1)[0].lower()]
                except KeyError:
                    pass

        try:
            release_dates_node = node['Released']
        except KeyError:
            for disco_entry in entry.disco_entries:
                if disco_entry.date:
                    release_dates = [disco_entry.date]
                    break
            else:
                release_dates = []
        else:
            if release_dates_node.children:
                release_dates = []
                for r_date in release_dates_node.sub_list.iter_flat():
                    if isinstance(r_date, String):
                        release_dates.append(datetime.strptime(r_date.value, '%Y.%m.%d').date())
                    else:
                        release_dates.append(datetime.strptime(r_date[0].value, '%Y.%m.%d').date())
            else:
                release_dates = [datetime.strptime(release_dates_node.value.value, '%Y.%m.%d').date()]

        for key, value in node.items():
            lc_key = key.lower().strip()
            if 'tracklist' in lc_key and not lc_key.startswith('dvd '):
                if lc_key != 'tracklist':
                    tl_edition = strip_style(key.rsplit(maxsplit=1)[0]).strip('"')
                    if tl_edition.lower() == 'cd':
                        tl_edition = None
                    if tl_edition:
                        edition = f'{edition} - {tl_edition}' if edition else tl_edition

                yield DiscographyEntryEdition(
                    album_name, entry_page, artist_link, release_dates, value, entry_type, edition or version,
                    find_language(value, lang, langs)
                )


def find_language(node: Node, lang: str, langs: Set[str]) -> Optional[str]:
    if lang:
        return lang
    else:
        if len(langs) == 1:
            return next(iter(langs))
        else:
            lang_cats = LangCat.categorize(node.raw.string, True)
            non_eng = [lc.full_name for lc in lang_cats.difference((LangCat.ENG,))]
            if len(non_eng) == 1:
                return non_eng[0]
            elif non_eng and langs:
                matching_langs = langs.intersection(non_eng)
                if len(matching_langs) == 1:
                    return next(iter(matching_langs))
    return None


def is_extra(text: str) -> bool:
    return bool(classify_extra(text))


def _split_name_parts(
        title: str, node: Optional[Node]
) -> Tuple[str, Optional[str], Optional[str], Dict[str, Any], Optional[str]]:
    """
    :param str title: The title
    :param Node|None node: The node to split
    :return tuple:
    """
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

    # log.debug(f'title={title!r} name_parts={name_parts!r}')

    if name_parts_str and LangCat.contains_any(name_parts_str, LangCat.asian_cats):
        name_parts = tuple(map(str.strip, name_parts_str.split(';')))
        if len(name_parts) == 1:
            non_eng = name_parts[0]
        elif len(name_parts) == 2:
            non_eng, lit_translation = name_parts
        else:
            raise ValueError(f'Unexpected name parts in node={node}')
    else:
        if node is None:
            title = original_title
        else:
            extra = name_parts_str

    extras = {}
    incomplete_extra = None
    if extra:
        # log.info(f'node={node!r} => extra={extra!r}', extra={'color': 'red'})
        incomplete_extra = process_extra(extras, extra)

    # log.debug(f'node={node!r} => title={title!r} non_eng={non_eng!r} lit={lit_translation!r} extras={extras}')
    return title, non_eng, lit_translation, extras, incomplete_extra


def process_incomplete_extra(extras: dict, incomplete_extra_type: str, node_iter: Iterator[Node]):
    nodes = []
    for node in node_iter:
        if isinstance(node, String):
            value = node.value
            if value == ')':
                break
            elif value.endswith(')'):
                node.value = value[:-1].strip()
                nodes.append(node)
                break
        nodes.append(node)

    extras[incomplete_extra_type] = CompoundNode.from_nodes(nodes, delim=' ')


def process_extra(extras: dict, extra: str) -> Optional[str]:
    """
    :param dict extras: The dict of extras in which the provided extra should be stored
    :param str extra: The extra text to be processed
    :return str|None: None if the provided extra was complete, or the type of the incomplete extra if it was not
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

    if extra_type == 'instrumental':
        extras[extra_type] = True
    elif extra_type == 'remix' and extra.lower() == 'remix':
        extras[extra_type] = True
    else:
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
    elif any(val in lc_text for val in (' ed.', 'edition')):
        return 'edition'

    return None
