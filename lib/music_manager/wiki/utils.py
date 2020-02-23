"""
:author: Doug Skrypa
"""

import logging
import re
from datetime import datetime, date

from ds_tools.unicode.languages import LangCat
from wiki_nodes.nodes import Node, Link, String, Template, CompoundNode
from ..matching.name import Name
from ..matching.spellcheck import is_english
from ..text.extraction import parenthesized

__all__ = ['parse_date', 'node_to_link_dict', 'parse_generasia_name']
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


def parse_generasia_name(node):
    log.debug(f'Processing node: {node}')
    try:
        date_pat = parse_generasia_name._date_pat
    except AttributeError:
        date_pat = parse_generasia_name._date_pat = re.compile(r'^\[\d{4}\.\d{2}\.\d{2}\]\s*(.*)$')

    # if isinstance(node, String):
    #     pass
    if not isinstance(node, list) and type(node) is not CompoundNode:
        nodes = iter([node])
        # raise TypeError(f'Unexpected type={type(node).__name__} for node={node}')
    else:
        nodes = iter(node)

    node = next(nodes)
    # after_date = None
    if isinstance(node, String):
        m = date_pat.match(node.value)
        if m:
            # after_date = m.group(1).strip()
            node = next(nodes)

    if isinstance(node, Link):
        title = node.show
    elif isinstance(node, String):
        title = node.value
    else:
        raise TypeError(f'Unexpected node type following date: {node}')

    non_eng, lit_translation, romanized, extra, name_parts = None, None, None, None, None
    node = next(nodes, None)
    if node and isinstance(node, String) and node.value == '-':
        # [date] [[primary artist]] - [[{romanized} (eng)]] (han; lit)
        # primary_artist = title
        node = next(nodes, None)
        if isinstance(node, Link):
            title = node.show
        else:
            raise TypeError(f'Unexpected node type following date: {node}')
        node = next(nodes, None)

    if node and isinstance(node, String):
        name_parts = parenthesized(node.value)
        if LangCat.contains_any(name_parts, LangCat.asian_cats):
            name_parts = tuple(map(str.strip, name_parts.split(';')))
        else:
            extra = name_parts
            name_parts = None

    if name_parts:
        if len(name_parts) == 1:
            non_eng = name_parts[0]
        elif len(name_parts) == 2:
            non_eng, lit_translation = name_parts
        else:
            raise ValueError(f'Unexpected name parts in node={node}')

    # [date] [[{romanized} (eng)]] (han; lit)
    #        ^_______title_______^
    # TODO: Handle OST(+Part) for checking romanization
    if '(' not in title:
        if non_eng:
            romanized = title
            eng_title = None
        else:
            eng_title = title
    elif non_eng:
        eng_title = parenthesized(title)
        if eng_title != title:                          # returns the full string if it didn't extract anything
            with_parens = f'({eng_title})'
            romanized, with_parens, remainder = map(str.strip, title.partition(with_parens))
            if remainder:                               # remix, etc
                extra = parenthesized(remainder)        # Remove parens around it if they exist
            elif eng_title.lower().endswith('ver.'):    # it wasn't an english part
                extra = eng_title                       # TODO: more cases than 'ver.'
                eng_title = None
        else:                                           # It only contained an opening (
            romanized = eng_title
            eng_title = None
    else:
        # TODO: handle [date] [[{track title} ({OST title})]]
        eng_title = title

    if romanized and non_eng:
        # log.debug(f'Verifying that rom={romanized!r} is a romanization of non_eng={non_eng!r}')
        if not Name(non_eng=non_eng).has_romanization(romanized):
            # log.debug('It is not')
            eng_title = romanized
            romanized = None
        elif is_english(romanized):
            log.debug(f'Text={romanized!r} is a romanization of non_eng={non_eng!r}, but it is also valid English')
            eng_title = romanized
            romanized = None
        # else:
        #     log.debug('It is')

    # log.debug(f'Name: eng={eng_title!r} non_eng={non_eng!r} rom={romanized!r} lit={lit_translation!r} extra={extra!r}')
    return Name(eng_title, non_eng, romanized, lit_translation, extra=extra)
