"""
:author: Doug Skrypa
"""

import re
from typing import Sequence, Iterable, Optional

__all__ = ['combine_with_parens', 'find_ordinal']

ORDINAL_TO_INT = {
    '1st': 1, '2nd': 2, '3rd': 3, '4th': 4, '5th': 5, '6th': 6, '7th': 7, '8th': 8, '9th': 9, '10th': 10,
    'first': 1, 'second': 2, 'third': 3, 'fourth': 4, 'fifth': 5, 'sixth': 6, 'seventh': 7, 'eighth': 8, 'ninth': 9,
    'tenth': 10, 'debut': 1
}
ORDINAL_SEARCH = re.compile('({})'.format('|'.join(ORDINAL_TO_INT)), re.IGNORECASE).search


def combine_with_parens(parts: Iterable[str]):
    if not isinstance(parts, Sequence):
        parts = list(parts)
    if len(parts) == 1:
        return parts[0]
    return '{} {}'.format(parts[0], ' '.join(f'({part})' for part in parts[1:]))


def find_ordinal(text: str) -> Optional[int]:
    if m := ORDINAL_SEARCH(text):
        return ORDINAL_TO_INT[m.group(1)]
    return None
