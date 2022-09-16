
import json
import logging
from argparse import REMAINDER
from typing import Union, Iterable

from ds_tools.argparsing.argparser import ArgParser
from .typing import PlexObjTypes

__all__ = ['pprint', 'parse_filters']
log = logging.getLogger(__name__)


def pprint(plex_obj):
    element = plex_obj._data
    obj = _extract(element)
    print(json.dumps(obj, indent=4, sort_keys=True))


def _extract(element):
    sub_elements = list(element)
    return {element.tag: {'attrib': element.attrib, 'contents': [_extract(e) for e in sub_elements]}}


def parse_filters(
    obj_type: str, title: Union[str, Iterable[str]], filters: Union[dict[str, str], str], escape: str, allow_inst: bool
) -> tuple['PlexObjTypes', dict[str, str]]:
    """
    :param obj_type: Type of Plex object to find (tracks, albums, artists, etc)
    :param title: Parts of the name of the object(s) to find, if searching by title__like2
    :param filters: Additional filters to apply during the search
    :param escape: Characters that should be escaped instead of treated as special regex characters
    :param allow_inst: Allow search results that include instrumental versions of songs
    :return: (str(normalized object type), dict(filters))
    """
    log.debug(f'parse_filters({obj_type=}, {title=}, {filters=}, {escape=}, {allow_inst=})')
    obj_type = obj_type[:-1] if obj_type.endswith('s') else obj_type
    escape_tbl = str.maketrans({c: '\\' + c for c in '()[]{}^$+*.?|\\' if c in escape})

    def escape_regex(text: str) -> str:
        return text.translate(escape_tbl)

    title = [title] if isinstance(title, str) else title
    title = escape_regex(' '.join(title)) if title else None

    if isinstance(filters, str):
        parser = ArgParser()
        parser.add_argument('ignore')
        parser.add_argument('query', nargs=REMAINDER)
        args = ['ignore', *filter(None, map(str.strip, filters.split()))]
        filters = parser.parse_with_dynamic_args('query', args)[1]

    for key, val in filters.items():
        try:
            op = key.rsplit('__', 1)[1]
        except Exception:  # noqa
            pass
        else:
            if op in ('regex', 'iregex', 'like', 'like_exact', 'not_like'):
                filters[key] = escape_regex(val)

    if title and title != '.*':
        if not any(c in title for c in '()[]{}^$+*.?' if c not in escape):
            filters.setdefault('title__icontains', title)
        else:
            filters.setdefault('title__like', title)

    if not allow_inst:
        filters.setdefault('title__not_like', r'inst(?:\.?|rumental)')

    log.debug(f'obj_type={obj_type}, title={title!r} => query={filters}')
    return obj_type, filters  # noqa
