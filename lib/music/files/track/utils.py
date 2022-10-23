"""
:author: Doug Skrypa
"""

from datetime import datetime, date
from typing import Optional
from unicodedata import normalize

from mutagen.id3 import POPM, USLT, APIC

from ds_tools.output.formatting import readable_bytes

from music.common.ratings import stars, stars_from_256

__all__ = ['tag_repr', 'parse_file_date', 'tag_id_to_name_map_for_type']


def tag_repr(tag_val, max_len=None, sub_len=None):
    if isinstance(tag_val, POPM):
        return stars(stars_from_256(tag_val.rating, 10))  # noqa
    elif isinstance(tag_val, APIC) and max_len is None and sub_len is None:
        size = readable_bytes(len(tag_val.data))  # noqa
        img_type = tag_val.type._pprint()  # noqa
        if img_type.startswith('cover'):
            img_type = '{} ({})'.format(*img_type.split())
        return f'<APIC[mime={tag_val.mime!r}, type={img_type!r}, desc={tag_val.desc!r}, size={size}]>'  # noqa
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


def tag_id_to_name_map_for_type(file_type: str) -> dict[str, str]:
    try:
        tag_id_to_name_map = tag_id_to_name_map_for_type._tag_id_to_name_map
    except AttributeError:
        from ...constants import TYPED_TAG_MAP
        tag_id_to_name_map = tag_id_to_name_map_for_type._tag_id_to_name_map = {}
        for name, type_tag_map in TYPED_TAG_MAP.items():
            for ftype, tag_id in type_tag_map.items():
                tag_id_to_name_map.setdefault(ftype, {})[tag_id] = name

    return tag_id_to_name_map[file_type]


def parse_file_date(dt_str) -> Optional[date]:
    for fmt in ('%Y%m%d', '%Y-%m-%d', '%Y'):
        try:
            return datetime.strptime(dt_str, fmt).date()
        except ValueError:
            pass
    return None
