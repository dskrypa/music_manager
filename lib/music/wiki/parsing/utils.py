"""
:author: Doug Skrypa
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Optional, Iterator, Type

from ds_tools.unicode import LangCat
from wiki_nodes import WikiPage, CompoundNode, Link, Node, String, ContainerNode, Table, Tag, N

from music.common.disco_entry import DiscoEntryType
from music.text.extraction import split_enclosed, has_unpaired, ends_with_enclosed, strip_enclosed
from music.text.name import Name

if TYPE_CHECKING:
    from ..album import DiscographyEntryPart
    from .abc import WikiParser

__all__ = [
    'FEAT_ARTIST_INDICATORS',
    'LANG_ABBREV_MAP',
    'NUM2INT',
    'get_artist_title',
    'find_language',
    'LANGUAGES',
    'replace_lang_abbrev',
    'PageIntro',
    'RawTracks',
    'find_nodes',
]
log = logging.getLogger(__name__)

FEAT_ARTIST_INDICATORS = ('with', 'feat.', 'feat ', 'featuring')
IS_SPLIT = re.compile(r' (?:is|are) (?:an|a|the|part \S+ of)', re.IGNORECASE).split
LANG_ABBREV_MAP = {
    'chinese': 'Chinese', 'chn': 'Chinese',
    'english': 'English', 'en': 'English', 'eng': 'English',
    'japanese': 'Japanese', 'jp': 'Japanese', 'jap': 'Japanese', 'jpn': 'Japanese',
    'korean': 'Korean', 'kr': 'Korean', 'kor': 'Korean', 'ko': 'Korean', 'hangul': 'Korean',
    'spanish': 'Spanish',
    'mandarin': 'Mandarin'
}
LANGUAGES = {lang.lower(): lang for lang in LANG_ABBREV_MAP.values()}
MULTI_LANG_NAME_SEARCH = re.compile(r'^([^(]+ \([^;]+?\))').search
LANG_PREFIX_SUB = re.compile(r'(?:{})\s?:'.format('|'.join(LANG_ABBREV_MAP)), re.IGNORECASE).sub
LANG_ABBREV_PAT = re.compile(r'(^|\s)({})(\s|$)'.format('|'.join(LANG_ABBREV_MAP)), re.IGNORECASE)
LIST_SPLIT = re.compile(r'[,;] ').split
NUM2INT = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'eight': 8, 'nine': 9}
WIKI_STYLE_SEARCHES = (
    re.compile(r"^(''''')(.+?)(\1)").search, re.compile(r"^(''')(.+?)(\1)").search, re.compile(r"^('')(.+?)(\1)").search
)


def _strify_node(node: ContainerNode):
    # log.debug(f'_strify_node({node!r})')
    parts = []
    for n in node:
        if not (isinstance(n, Tag) and n.name == 'ref'):
            parts.extend(n.strings())

    return ' '.join(parts)


class PageIntro:
    __slots__ = ('page', 'raw_intro', 'intro')
    _born_date_match = re.compile(r'^(.*?)\s*\(born \w+ \d+, \d{4}\)$', re.IGNORECASE).match
    AKA_SYNONYMS = ('also known as', 'also known simply as')
    TO_RM_PARENTHESIZED_PREFIXES = ('(stylized', '(short for', '(also known')
    FIRST_SENTENCE_SECTION_PARTITIONERS = (', born', ', known professionally as', ', formerly known as')

    def __init__(self, page: WikiPage):
        self.page = page
        self.raw_intro = intro = page.intro(True)
        if isinstance(intro, ContainerNode):
            self.intro = _strify_node(intro)
        elif isinstance(intro, String):
            self.intro = intro.value
        else:
            try:
                raise ValueError(f'Unexpected intro on {page}:\n{self.raw_intro.pformat()}')
            except AttributeError:
                raise ValueError(f'Unexpected intro on {page}: {self.raw_intro!r}') from None

    def _to_process(self) -> list[str]:
        # Partition the first sentence of the intro into sections that should be processed individually
        first_string = IS_SPLIT(self.intro, 1)[0].strip()
        log.debug(f'{first_string=!r}')

        parts = [first_string]
        for partitioner in self.FIRST_SENTENCE_SECTION_PARTITIONERS:
            parts = [
                p
                for part in parts
                for p in (p.strip().rstrip(',').strip() for p in part.partition(partitioner)[::2])
                if p
            ]

        return parts

    def names(self) -> Iterator[Name]:
        for name_str in self._to_process():
            if m := self._born_date_match(name_str):
                name_str = m.group(1).strip()
            if (m := MULTI_LANG_NAME_SEARCH(name_str)) and not has_unpaired(m_str := m.group(1)):
                # log.debug(f'Found multi-lang name match={m} ({m_str=})')
                yield from self._names_from_multi_lang_str(m_str)
            else:
                yield from self._split_name_parts(self._base_name_str(name_str))

    def _names_from_multi_lang_str(self, m_str: str) -> Iterator[Name]:
        cleaned = rm_lang_prefix(m_str)
        if split_prefix := next((p for p in self.TO_RM_PARENTHESIZED_PREFIXES if p in cleaned), None):
            cleaned = cleaned.partition(split_prefix)[0].strip()

        # log.debug(f'Cleaned name: {cleaned!r}')
        parts = split_enclosed(cleaned, maxsplit=1)
        if len(parts) == 2:
            if names := _multi_lang_names(*parts):
                # log.debug(f'Yielding from _multi_lang_names={names} for {parts=}')
                for name in names:
                    if name.english and name.extra and not name.non_eng:
                        yield Name('{} ({})'.format(*parts))
                    else:
                        yield name
            else:
                yield Name(cleaned)
        else:
            yield Name.from_enclosed(cleaned)

    def _base_name_str(self, first_string: str) -> str:
        try:
            name = first_string[:first_string.rindex(')') + 1]
        except ValueError:
            if '(' in first_string:
                name = first_string + ')'
                if name.endswith('()'):
                    name = name[:-2].strip()
            else:
                name = first_string

        if name.startswith('"'):
            if name.count('"') == 1:
                name = name[1:]
            elif name.endswith('"'):
                name = name[1:-1]

        return name

    def _split_name_parts(self, name: str) -> Iterator[Name]:
        # log.debug(f'_split_name_parts({name=})')
        try:
            first_part, paren_part = split_enclosed(name, reverse=True, maxsplit=1)
        except ValueError:
            # log.debug(f'split_enclosed({name!r}) failed')
            raw_intro = self.raw_intro.raw.string
            if m := next((search(raw_intro) for search in WIKI_STYLE_SEARCHES), None):  # noqa
                name = m.group(2)
            name = strip_enclosed(name.replace(' : ', ': '))
            yield Name(name)
        else:
            yield from self._process_name_parts(name, first_part, paren_part)

    def _process_name_parts(self, name: str, first_part: str, paren_part: str) -> Iterator[Name]:
        # log.debug(f'_process_name_parts({name!r}, {first_part!r}, {paren_part!r})')
        while _should_resplit(first_part, paren_part):
            # log.debug(f'Split {name=!r} => {first_part=!r} {paren_part=!r}; re-splitting...', extra={'color': 11})
            try:
                first_part, paren_part = split_enclosed(first_part, reverse=True, maxsplit=1)
            except ValueError:
                # log.debug(f'Could not re-split {first_part=}')
                break
            # else:
            #     log.debug('re-split')

        # log.debug(f'Split {name=!r} => {first_part=!r} {paren_part=!r}')
        if paren_part.lower() == 'repackage':
            yield Name.from_enclosed(first_part, extra={'repackage': True})
        elif '; ' in paren_part:
            # log.debug('Found ;')
            yield from _multi_lang_names(first_part, paren_part)
        elif ', and' in paren_part:
            # log.debug('Found ", and"')
            yield from self._process_name_list(first_part, paren_part)
        else:
            # log.debug('No ;/and')
            if aka := next((val for val in self.AKA_SYNONYMS if paren_part.startswith(val)), None):
                paren_part = paren_part[len(aka):].strip()
                if ends_with_enclosed(paren_part):
                    eng_2, non_eng = split_enclosed(paren_part, reverse=True, maxsplit=1)
                    yield Name.from_parts((first_part, non_eng))
                    yield Name.from_parts((eng_2, non_eng))
                else:
                    yield Name.from_parts((first_part, paren_part))
            elif 'remix' in paren_part.lower():
                yield Name(f'{first_part} ({paren_part})')
            else:
                if ' is ' in self.intro and '(' not in name:
                    paren_part = paren_part.partition(' is ')[0]
                    yield Name(f'\'{first_part}\' {paren_part}')  # Example: The_ReVe_Festival_Finale
                elif LangCat.categorize(first_part) == LangCat.categorize(paren_part):
                    yield Name.from_enclosed(first_part)
                else:
                    yield Name.from_parts((first_part, paren_part))

    def _process_name_list(self, first_part: str, paren_part: str):
        for part in map(str.strip, paren_part.split(', and')):
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
                    name_1 = Name.from_parts((first_part, part_a))
                    name_1.update(romanized=part_b)
                    yield name_1
                else:
                    name_1 = Name.from_parts((first_part, part_a))
                    name_2 = Name.from_parts((alias, part_a))
                    name_2.update(romanized=romanized)
                    name_1.update(romanized=romanized, versions={name_2})
                    yield name_1


class RawTracks:
    __slots__ = ('raw_tracks',)

    def __init__(self, raw_tracks):
        self.raw_tracks = raw_tracks

    def get_names(self, part: DiscographyEntryPart, parser: WikiParser) -> list[Name]:
        if self.raw_tracks is None:
            if part.edition.type == DiscoEntryType.Single:
                return [parser.parse_single_page_track_name(part.edition.page)]
            else:
                log.debug(f'No tracks found for {self}')
                return []
        elif isinstance(self.raw_tracks, Table):
            return [parser.parse_track_name(row) for row in self.raw_tracks]
        else:
            # if isinstance(self._tracks, ListNode):
            #     log.debug(f'Processing tracks for {self}')
            return [parser.parse_track_name(node) for node in self.raw_tracks.iter_flat()]


def _should_resplit(first_part, paren_part) -> bool:
    if len(first_part) > 2 * len(paren_part):
        return True
    return paren_part.startswith('is a') or paren_part.startswith('was a') and '(' in first_part


def _multi_lang_names(primary, parts):
    first_part_lang = LangCat.categorize(primary)
    parts = list(map(rm_lang_prefix, LIST_SPLIT(parts)))
    names = []
    for part in parts:
        if LangCat.categorize(part) != first_part_lang and not part.startswith('stylized '):
            names.append(Name.from_parts((primary, part)))
        elif part.startswith('lit. '):
            part = strip_enclosed(part.split(maxsplit=1)[1])
            for _name in names:
                _name.update(lit_translation=part)
    return names


def find_language(node: Node, lang: Optional[str], langs: set[str]) -> Optional[str]:
    if lang:
        return lang
    elif not node:
        return None
    elif len(langs) == 1:
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


def replace_lang_abbrev(text: str) -> str:
    if m := LANG_ABBREV_PAT.search(text):
        return LANG_ABBREV_PAT.sub(fr'\1{LANG_ABBREV_MAP[m.group(2).lower()]}\3', text)
    return text


def get_artist_title(node: Node, entry_page: WikiPage):
    if isinstance(node, Link):
        return node.title
    elif isinstance(node, CompoundNode) and isinstance(node[0], Link):
        return node[0].title
    else:
        log.debug(f'Unexpected member format on page={entry_page}: {node}')
        return None


def rm_lang_prefix(text: str) -> str:
    return LANG_PREFIX_SUB('', text).strip()


def find_nodes(nodes, node_cls: Type[N]) -> list[N]:
    if not nodes:
        return []
    elif isinstance(nodes, node_cls):
        return [nodes]
    try:
        return list(nodes.find_all(node_cls))  # noqa
    except AttributeError:
        pass
    try:
        nodes = tuple(nodes)
    except TypeError:  # It's not iterable, and it's not a Node
        return []

    found = [node for node in nodes if isinstance(node, node_cls)]
    for node in nodes:
        try:
            found.extend(node.find_all(node_cls))
        except AttributeError:
            pass

    return found
