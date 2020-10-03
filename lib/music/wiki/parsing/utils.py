"""
:author: Doug Skrypa
"""

import logging
import re
from typing import Optional, Iterator, Set

from ds_tools.unicode import LangCat
from wiki_nodes import WikiPage, CompoundNode, Link, Node, String, Template, MappingNode
from ...text.extraction import split_enclosed, has_unpaired, ends_with_enclosed, strip_enclosed
from ...text.name import Name

__all__ = [
    'FEAT_ARTIST_INDICATORS', 'LANG_ABBREV_MAP', 'NUM2INT', 'name_from_intro', 'get_artist_title', 'find_language',
    'LANGUAGES', 'replace_lang_abbrev'
]
log = logging.getLogger(__name__)

FEAT_ARTIST_INDICATORS = ('with', 'feat.', 'feat ', 'featuring')
IS_SPLIT = re.compile(r' is (?:a|the)', re.IGNORECASE).split
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


def _strify_node(node: CompoundNode):
    # log.debug(f'_strify_node({node!r})')
    parts = []
    for n in node:
        if isinstance(n, Link):
            parts.append(n.show)
        elif isinstance(n, String):
            parts.append(n.value)
        elif isinstance(n, Template):
            if isinstance(n.value, String):
                parts.append(n.value.value)
            elif n.name.lower() == 'korean' and isinstance(n.value, MappingNode):
                if value := n.value.get('hangul'):
                    parts.append(value.value)
        else:
            break
    return ' '.join(parts)


def name_from_intro(page: WikiPage) -> Iterator[Name]:
    _intro = intro = page.intro(True)
    if isinstance(intro, CompoundNode):
        intro = _strify_node(intro)
    elif isinstance(intro, String):
        intro = intro.value
    else:
        intro = None

    if intro:
        first_string = IS_SPLIT(intro, 1)[0]
        # log.debug(f'{first_string=!r}')
    else:
        try:
            raise ValueError(f'Unexpected intro on {page}:\n{_intro.pformat()}')
        except AttributeError:
            raise ValueError(f'Unexpected intro on {page}: {_intro!r}') from None

    if (m := MULTI_LANG_NAME_SEARCH(first_string)) and not has_unpaired(m_str := m.group(1)):
        # log.debug(f'Found multi-lang name match: {m}')
        # noinspection PyUnboundLocalVariable
        cleaned = rm_lang_prefix(m_str)
        if split_prefix := next((p for p in ('(stylized', '(short for') if p in cleaned), None):
            cleaned = cleaned.partition(split_prefix)[0].strip()

        # log.debug(f'Cleaned name: {cleaned!r}')
        parts = split_enclosed(cleaned, maxsplit=1)
        if len(parts) == 2:
            # log.debug(f'Yielding from _multi_lang_names for {parts=}')
            names = _multi_lang_names(*parts)
            if names:
                yield from names
            else:
                yield Name(cleaned)
        else:
            yield Name.from_enclosed(cleaned)
    else:
        try:
            name = first_string[:first_string.rindex(')') + 1]
        except ValueError:
            if '(' in first_string:
                name = first_string + ')'
                if name.endswith('()'):
                    name = name[:-2].strip()
            else:
                name = first_string

        # log.debug(f'Found {name=!r}')
        try:
            first_part, paren_part = split_enclosed(name, reverse=True, maxsplit=1)
        except ValueError:
            # log.debug(f'split_enclosed({name!r}) failed')
            raw_intro = _intro.raw.string
            if m := next((search(raw_intro) for search in WIKI_STYLE_SEARCHES), None):
                name = m.group(2)
            name = strip_enclosed(name.replace(' : ', ': '))
            yield Name(name)
        else:
            while len(first_part) > 2 * len(paren_part):
                # log.debug(f'Split {name=!r} => {first_part=!r} {paren_part=!r}; attempting re-split')
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
                    if ' is ' in intro and '(' not in name:
                        paren_part = paren_part.partition(' is ')[0]
                        yield Name(f'\'{first_part}\' {paren_part}')    # Example: The_ReVe_Festival_Finale
                    elif LangCat.categorize(first_part) == LangCat.categorize(paren_part):
                        yield Name.from_enclosed(first_part)
                    else:
                        yield Name.from_parts((first_part, paren_part))


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


def replace_lang_abbrev(text: str) -> str:
    if m := LANG_ABBREV_PAT.search(text):
        abbrev = m.group(2).lower()
        lang = LANG_ABBREV_MAP[abbrev]
        return LANG_ABBREV_PAT.sub(r'\1{}\3'.format(lang), text)
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
