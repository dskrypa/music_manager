"""
:author: Doug Skrypa
"""

import logging
from datetime import datetime, date
from typing import Optional, Dict
from unicodedata import normalize

from mutagen.id3 import POPM, USLT, APIC

from ...common.utils import stars

__all__ = ['RATING_RANGES', 'tag_repr', 'stars_from_256', 'parse_file_date', 'tag_id_to_name_map_for_type']
log = logging.getLogger(__name__)

RATING_RANGES = [(1, 31, 15), (32, 95, 64), (96, 159, 128), (160, 223, 196), (224, 255, 255)]


def tag_repr(tag_val, max_len=None, sub_len=None):
    if isinstance(tag_val, POPM):
        # noinspection PyUnresolvedReferences
        return stars(stars_from_256(tag_val.rating, 10))
    elif isinstance(tag_val, APIC) and max_len is None and sub_len is None:
        return '<APIC>'
    elif isinstance(tag_val, USLT) and max_len is None and sub_len is None:
        max_len, sub_len = 45, 20
    else:
        max_len = max_len or 125
        sub_len = sub_len or 25

    try:
        table = tag_repr._table
    except AttributeError:
        import string
        # Translate whitespace characters (such as \n, \r, etc.) to their escape sequences
        table = tag_repr._table = str.maketrans(
            {c: c.encode('unicode_escape').decode('utf-8') for c in string.whitespace}
        )

    tag_val = normalize('NFC', str(tag_val)).translate(table)
    if len(tag_val) > max_len:
        return '{}...{}'.format(tag_val[:sub_len], tag_val[-sub_len:])
    return tag_val


def tag_id_to_name_map_for_type(file_type: str) -> Dict[str, str]:
    try:
        tag_id_to_name_map = tag_id_to_name_map_for_type._tag_id_to_name_map
    except AttributeError:
        from ...constants import TYPED_TAG_MAP
        tag_id_to_name_map = tag_id_to_name_map_for_type._tag_id_to_name_map = {}
        for name, type_tag_map in TYPED_TAG_MAP.items():
            for ftype, tag_id in type_tag_map.items():
                tag_id_to_name_map.setdefault(ftype, {})[tag_id] = name

    return tag_id_to_name_map[file_type]


def stars_from_256(rating: int, out_of=5) -> int:
    if not (0 <= rating <= 255):
        raise ValueError(f'{rating=} is outside the range of 0-255')
    elif out_of == 256:
        return rating
    elif out_of not in (5, 10):
        raise ValueError(f'{out_of=} is invalid - must be 5, 10, or 256')

    for stars_5, (a, b, c) in enumerate(RATING_RANGES, 1):
        if a <= rating <= b:
            if out_of == 5:
                return stars_5
            a, b, c = RATING_RANGES[stars_5 - 1]
            if stars_5 == 1 and rating < c:
                return 1
            stars_10 = stars_5 * 2
            return stars_10 + 1 if rating > c else stars_10


def parse_file_date(dt_str) -> Optional[date]:
    for fmt in ('%Y%m%d', '%Y-%m-%d', '%Y'):
        try:
            return datetime.strptime(dt_str, fmt).date()
        except ValueError:
            pass
    return None
