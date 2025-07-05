"""
Utils for dumping raw Plex object data
"""

from __future__ import annotations

import json

__all__ = ['pprint']

Filters = dict[str, str]


def pprint(plex_obj):
    print(json.dumps(_extract(plex_obj._data), indent=4, sort_keys=True, ensure_ascii=False))


def _extract(element):
    sub_elements = list(element)
    return {element.tag: {'attrib': element.attrib, 'contents': [_extract(e) for e in sub_elements]}}
