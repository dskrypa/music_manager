"""
:author: Doug Skrypa
"""

import logging
import re
from typing import Optional

__all__ = ['FEAT_ARTIST_INDICATORS', 'LANG_ABBREV_MAP', 'NUM2INT', 'ORDINAL_TO_INT', 'find_ordinal']
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
