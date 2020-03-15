"""
:author: Doug Skrypa
"""

import logging

__all__ = ['FEAT_ARTIST_INDICATORS', 'LANG_ABBREV_MAP', 'NUM2INT', 'NUMS']
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
NUMS = {
    'first': '1st', 'second': '2nd', 'third': '3rd', 'fourth': '4th', 'fifth': '5th', 'sixth': '6th',
    'seventh': '7th', 'eighth': '8th', 'ninth': '9th', 'tenth': '10th', 'debut': '1st'
}
