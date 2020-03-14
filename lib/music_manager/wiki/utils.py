"""
:author: Doug Skrypa
"""

import logging

from wiki_nodes.nodes import Node, Link, String, Template, CompoundNode

__all__ = ['node_to_link_dict']
log = logging.getLogger(__name__)


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
    elif isinstance(node, CompoundNode):
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
