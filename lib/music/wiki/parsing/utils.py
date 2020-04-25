"""
:author: Doug Skrypa
"""

import logging
import re
from typing import Optional, Iterator, Set

from ds_tools.unicode import LangCat
from wiki_nodes import WikiPage, CompoundNode, Link, Node
from ...text import split_enclosed, Name, has_unpaired, ends_with_enclosed

__all__ = [
    'FEAT_ARTIST_INDICATORS', 'LANG_ABBREV_MAP', 'NUM2INT', 'ORDINAL_TO_INT', 'find_ordinal', 'name_from_intro',
    'get_artist_title', 'find_language'
]
log = logging.getLogger(__name__)

FEAT_ARTIST_INDICATORS = ('with', 'feat.', 'feat ', 'featuring')
LANG_ABBREV_MAP = {
    'chinese': 'Chinese', 'chn': 'Chinese',
    'english': 'English', 'en': 'English', 'eng': 'English',
    'japanese': 'Japanese', 'jp': 'Japanese', 'jap': 'Japanese', 'jpn': 'Japanese',
    'korean': 'Korean', 'kr': 'Korean', 'kor': 'Korean', 'ko': 'Korean',
    'spanish': 'Spanish',
    'mandarin': 'Mandarin'
}
MULTI_LANG_NAME_SEARCH = re.compile(r'^([^(]+ \([^;]+?\))').search
LANG_PREFIX_SUB = re.compile(r'(?:{}):'.format('|'.join(LANG_ABBREV_MAP)), re.IGNORECASE).sub
NUM2INT = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'eight': 8, 'nine': 9}
ORDINAL_TO_INT = {
    '1st': 1, '2nd': 2, '3rd': 3, '4th': 4, '5th': 5, '6th': 6, '7th': 7, '8th': 8, '9th': 9, '10th': 10,
    'first': 1, 'second': 2, 'third': 3, 'fourth': 4, 'fifth': 5, 'sixth': 6, 'seventh': 7, 'eighth': 8, 'ninth': 9,
    'tenth': 10, 'debut': 1
}
ORDINAL_SEARCH = re.compile('({})'.format('|'.join(ORDINAL_TO_INT)), re.IGNORECASE).search


def find_ordinal(text: str) -> Optional[int]:
    if m := ORDINAL_SEARCH(text):
        return ORDINAL_TO_INT[m.group(1)]
    return None


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


def name_from_intro(artist_page: WikiPage) -> Iterator[Name]:
    intro = artist_page.intro
    if isinstance(intro, CompoundNode):
        intro = intro[0]
    if intro:
        first_string = intro.value
    else:
        raise ValueError(f'Unexpected intro on {artist_page}:\n{artist_page.intro.pformat()}')

    if (m := MULTI_LANG_NAME_SEARCH(first_string)) and not has_unpaired(m_str := m.group(1)):
        # log.debug(f'Found multi-lang name match: {m}')
        # noinspection PyUnboundLocalVariable
        cleaned = rm_lang_prefix(m_str)
        # log.debug(f'Without lang prefix: {cleaned!r}')
        if delim := next((c for c in ';,' if c in cleaned), None):
            cleaned = cleaned.split(delim, 1)[0].strip() + ')'
        # log.debug(f'Cleaned name: {cleaned!r}')
        yield Name.from_enclosed(cleaned)
    else:
        # log.debug(f'Found {first_string=!r}')
        try:
            name = first_string[:first_string.rindex(')') + 1]
        except ValueError:
            if '(' in first_string:
                name = first_string + ')'
            else:
                name = first_string

        # log.debug(f'Found {name=!r}')
        try:
            first_part, paren_part = split_enclosed(name, reverse=True, maxsplit=1)
        except ValueError:
            yield Name(name)
        else:
            if '; ' in paren_part:
                # log.debug('Found ;')
                first_part_lang = LangCat.categorize(first_part)
                for part in map(rm_lang_prefix, paren_part.split('; ')):
                    if LangCat.categorize(part) != first_part_lang and not part.startswith('stylized '):
                        yield Name.from_parts((first_part, part))
            elif ', and' in paren_part:
                # log.debug('Found ", and"')
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
                            name_1.update(romanized=romanized, versions=[name_2])
                            yield name_1
            else:
                # log.debug('No ;/and')
                if paren_part.startswith('also known as'):
                    paren_part = paren_part[13:].strip()
                    if ends_with_enclosed(paren_part):
                        eng_2, non_eng = split_enclosed(paren_part, reverse=True, maxsplit=1)
                        yield Name.from_parts((first_part, non_eng))
                        yield Name.from_parts((eng_2, non_eng))
                    else:
                        yield Name.from_parts((first_part, paren_part))
                else:
                    if LangCat.categorize(first_part) == LangCat.categorize(paren_part):
                        yield Name.from_enclosed(first_part)
                    else:
                        yield Name.from_parts((first_part, paren_part))


def find_language(node: Node, lang: Optional[str], langs: Set[str]) -> Optional[str]:
    if lang:
        return lang
    elif node:
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
