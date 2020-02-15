"""
:author: Doug Skrypa
"""

import logging
from datetime import datetime, date

from ds_tools.wiki.nodes import Node, Link, String, MixedNode, Template

__all__ = ['parse_date']
log = logging.getLogger(__name__)
DATE_FORMATS = ('%Y-%b-%d', '%Y-%m-%d', '%Y.%m.%d', '%B %d, %Y', '%d %B %Y')


def parse_date(value):
    """
    :param str|datetime|None value: The value from which a date should be parsed
    :return: The parsed date
    """
    if value is None or isinstance(value, datetime):
        return value
    elif isinstance(value, date):
        return datetime.fromordinal(value.toordinal())

    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass

    raise ValueError(f'Unable to parse date from {value!r} using common date formats')


def node_to_link_dict(node):
    if not node:
        return None
    elif not isinstance(node, Node):
        raise TypeError(f'Unexpected node type={type(node).__name__}')
    elif isinstance(node, Template) and node.name == 'n/a':
        return None

    as_dict = {}
    if isinstance(node, String):
        as_dict[node.value] = None
    elif isinstance(node, Link):
        as_dict[node.text or node.title] = node
    elif isinstance(node, MixedNode):
        if len(node) == 2:
            a, b = node
            if isinstance(a, Link) and isinstance(b, String):
                if b.value == 'OST':
                    as_dict[f'{a.text or a.title} OST'] = a
                elif b.value.startswith('and '):
                    as_dict[a.text or a.title] = a
                    as_dict[b.value[4:].strip()] = None
                else:
                    raise ValueError(f'Unexpected content for node={node}')
            elif isinstance(a, String) and isinstance(b, Link):
                if a.value.endswith(' and'):
                    as_dict[b.text or b.title] = b
                    as_dict[a.value[:-4].strip()] = None
                else:
                    raise ValueError(f'Unexpected content for node={node}')
        elif len(node) == 3:
            a, b, c = node
            if isinstance(a, Link) and isinstance(b, String) and isinstance(c, Link):
                b = b.value
                if b.startswith('OST '):
                    as_dict[f'{a.text or a.title} OST'] = a
                    b = b[4:].strip()
                else:
                    as_dict[a.text or a.title] = a
                if b == 'and':
                    as_dict[c.text or c.title] = c
                else:
                    raise ValueError(f'Unexpected content for node={node}')
            elif isinstance(a, String) and isinstance(b, Link) and isinstance(c, String):
                a, c = map(lambda n: n.value.strip("'"), (a, c))
                if not a and c == 'OST':
                    as_dict[f'{b.text or b.title} OST'] = b
                else:
                    raise ValueError(f'Unexpected content for node={node}')
            else:
                raise ValueError(f'Unexpected content for node={node}')
    else:
        raise ValueError(f'Unexpected content for node={node}')

    for to_rm in ('Non-album single', 'Non-album singles'):
        if to_rm in as_dict:
            del as_dict[to_rm]

    return as_dict
