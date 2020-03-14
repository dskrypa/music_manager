"""
:author: Doug Skrypa
"""

import logging
import re

from ds_tools.unicode.languages import LangCat
from wiki_nodes.nodes import Node, Link, String, CompoundNode
from ...text.extraction import parenthesized, partition_enclosed
from ...text.name import Name
from ...text.spellcheck import is_english, english_probability

__all__ = ['parse_generasia_name']
log = logging.getLogger(__name__)


def parse_generasia_name(node: Node):
    # log.debug(f'Processing node: {node}')
    _node = node
    try:
        date_pat = parse_generasia_name._date_pat
        ost_pat = parse_generasia_name._ost_pat
    except AttributeError:
        date_pat = parse_generasia_name._date_pat = re.compile(r'^\[\d{4}\.\d{2}\.\d{2}\]\s*(.*)$')
        ost_pat = parse_generasia_name._ost_pat = re.compile(r'\sOST(?:\s*|$)')

    if not isinstance(node, list) and type(node) is not CompoundNode:
        nodes = iter([node])
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

    node = next(nodes, None)
    if node and isinstance(node, String):
        node_str = node.value
        if node_str == '-' or node_str.startswith('&') and node_str.endswith('-'):
            # [date] [[primary artist]] - [[{romanized} (eng)]] (han; lit)
            # primary_artist = title
            node = next(nodes, None)
            if isinstance(node, Link):
                title = node.show
            else:
                raise TypeError(f'Unexpected node type following date: {node}')
            node = next(nodes, None)

    title, non_eng, lit_translation, extra = _split_name_parts(title, node)

    # log.debug(f'title={title!r} non_eng={non_eng!r} lit_translation={lit_translation!r} extra={extra!r}')

    eng_title, romanized = None, None
    extras = [extra] if extra else []
    if not title.endswith(')') and ')' in title:
        pos = title.rindex(')') + 1
        extras.append(title[pos:].strip())
        title = title[:pos].strip()

    # [date] [[{romanized} (eng)]] (han; lit)
    #        ^_______title_______^
    # TODO: Handle OST(+Part) for checking romanization
    if title.endswith(')') and '(' in title:
        if non_eng:
            non_eng_name = Name(non_eng=non_eng)
            if non_eng.endswith(')') and '(' in non_eng and non_eng_name.has_romanization(title):
                if is_english(title):
                    eng_title = title
                else:
                    romanized = title
            else:
                a, b, _ = partition_enclosed(title, reverse=True)
                if a.endswith(')') and '(' in a:
                    extras.append(b)
                    a, b, _ = partition_enclosed(a, reverse=True)

                # log.debug(f'a={a!r} b={b!r}')
                if non_eng_name.has_romanization(a):
                    # log.debug(f'romanized({non_eng!r}) ==> {a!r}')
                    if _node.root and _node.root.title == title:
                        # log.debug(f'_node.root.title matches title')
                        if is_english(a):
                            # log.debug(f'a={a!r} is the English title')
                            eng_title = title
                        else:
                            # log.debug(f'a={a!r} is the Romanized title')
                            romanized = title
                        non_eng = title.replace(a, non_eng)
                        lit_translation = title.replace(a, lit_translation) if lit_translation else None
                        # log.debug(f'eng_title={eng_title!r} non_eng={non_eng!r} romanized={romanized!r} lit_translation={lit_translation!r} extra={extra!r}')
                    else:
                        if is_english(a):
                            # log.debug(f'Text={a!r} is a romanization of non_eng={non_eng!r}, but it is also valid English')
                            eng_title = a
                        else:
                            romanized = a

                        if is_extra(b):
                            extras.append(b)
                        elif eng_title:
                            eng_title = f'{eng_title} ({b})'
                        else:
                            eng_title = b
                else:
                    if _node.root and _node.root.title == title:
                        eng_title = title
                    else:
                        if is_extra(b):
                            eng_title = a
                            extras.append(b)
                        else:
                            eng_title = f'{a} ({b})'
        else:
            a, b, _ = partition_enclosed(title, reverse=True)
            if ost_pat.search(b) or is_extra(b):
                eng_title = a
                extras.append(b)
            else:
                eng_title = title

            if english_probability(eng_title) < 0.5:
                romanized, eng_title = eng_title, None

    else:
        if non_eng and Name(non_eng=non_eng).has_romanization(title):
            if is_english(title):
                eng_title = title
            else:
                romanized = title
                if lit_translation and ' / ' in lit_translation:
                    lit, eng = lit_translation.split(' / ', 1)
                    if f'{lit} / {eng}' not in _node.raw.string:    # Make sure it had formatting after lit / before eng
                        eng_title, lit_translation = eng, lit
        else:
            eng_title = title

    # log.debug(f'Name: eng={eng_title!r} non_eng={non_eng!r} rom={romanized!r} lit={lit_translation!r} extra={extra!r}')
    return Name(eng_title, non_eng, romanized, lit_translation, extra=extras[0] if len(extras) == 1 else extras or None)


def is_extra(text):
    # TODO: more cases
    lc_text = text.lower()
    if lc_text.endswith('ver.'):
        return True
    elif lc_text.startswith('inst.'):
        return True
    return False


def _split_name_parts(title, node):
    """
    :param str title: The title
    :param Node|None node: The node to split
    :return tuple:
    """
    original_title = title
    non_eng, lit_translation, extra, name_parts = None, None, None, None
    if isinstance(node, String):
        name_parts = parenthesized(node.value)
    elif node is None:
        if title.endswith(')'):
            try:
                title, name_parts, _ = partition_enclosed(title, reverse=True)
            except ValueError:
                pass

    # log.debug(f'title={title!r} name_parts={name_parts!r}')

    if name_parts and LangCat.contains_any(name_parts, LangCat.asian_cats):
        name_parts = tuple(map(str.strip, name_parts.split(';')))
    else:
        if node is None:
            title = original_title
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

    if extra and extra.startswith('(') and ')' not in extra:
        extra = extra[1:]
        if extra.lower().startswith('feat'):
            extra = None

    # log.debug(f'node={node!r} => title={title!r} non_eng={non_eng!r} lit_translation={lit_translation!r} extra={extra!r}')
    return title, non_eng, lit_translation, extra
