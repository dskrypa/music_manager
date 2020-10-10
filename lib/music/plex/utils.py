
import json

__all__ = ['pprint']


def pprint(plex_obj):
    element = plex_obj._data
    obj = _extract(element)
    print(json.dumps(obj, indent=4, sort_keys=True))


def _extract(element):
    sub_elements = list(element)
    return {element.tag: {'attrib': element.attrib, 'contents': [_extract(e) for e in sub_elements]}}
