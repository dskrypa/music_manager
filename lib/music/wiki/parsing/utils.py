"""
:author: Doug Skrypa
"""

import logging
import re
from typing import Optional, Iterator

from wiki_nodes import WikiPage, CompoundNode
from ...text import split_enclosed, Name

__all__ = [
    'FEAT_ARTIST_INDICATORS', 'LANG_ABBREV_MAP', 'NUM2INT', 'ORDINAL_TO_INT', 'find_ordinal', 'artist_name_from_intro'
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


def artist_name_from_intro(artist_page: WikiPage) -> Iterator[Name]:
    intro = artist_page.intro
    if isinstance(intro, CompoundNode):
        intro = intro[0]
    if intro:
        first_string = intro.value
    else:
        raise RuntimeError(f'Unexpected intro on {artist_page}:\n{artist_page.intro}')

    if m := MULTI_LANG_NAME_SEARCH(first_string):
        yield Name.from_enclosed(m.group(1))
    else:
        # try:
        name = first_string[:first_string.rindex(')') + 1]
        # except ValueError:
        #     log.error(f'Unable to find name in {artist_page} - {first_string=!r}', extra={'color': 'red'})
        #     log.debug(f'Categories for {artist_page}: {artist_page.categories}')
        #     raise

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
