"""
:author: Doug Skrypa
"""

import logging
from collections import defaultdict
from typing import Iterable, Dict, Optional, Tuple, List as ListType

from wiki_nodes import MediaWikiClient, WikiPage, Node, Link, String, Template, CompoundNode, List
from .exceptions import NoLinkSite, NoLinkTarget

__all__ = ['node_to_link_dict', 'site_titles_map', 'link_client_and_title', 'disambiguation_links', 'page_name']
log = logging.getLogger(__name__)


def link_client_and_title(link: Link) -> Tuple[MediaWikiClient, str]:
    if not link.source_site:
        raise NoLinkSite(link)
    mw_client = MediaWikiClient(link.source_site)
    title = link.title
    if link.interwiki:
        iw_key, title = link.iw_key_title
        mw_client = mw_client.interwiki_client(iw_key)
    elif not title:
        raise NoLinkTarget(link)
    return mw_client, title


def site_titles_map(links: Iterable[Link]) -> Dict[MediaWikiClient, Dict[str, Link]]:
    site_map = defaultdict(dict)
    for link in links:
        mw_client, title = link_client_and_title(link)
        site_map[mw_client][title] = link
    return site_map


def node_to_link_dict(node: Node) -> Optional[Dict[str, Optional[Node]]]:
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


def disambiguation_links(page: WikiPage) -> ListType[Link]:
    links = []
    for section in page:
        if isinstance(section.content, List):
            for entry in section.content.iter_flat():
                if isinstance(entry[0], Link):
                    links.append(entry[0])
        else:
            for link_list in section.content.find_all(List):
                for entry in link_list.iter_flat():
                    if isinstance(entry[0], Link):
                        links.append(entry[0])

    return links


def page_name(page: WikiPage) -> str:
    name = page.title
    if page.infobox:
        try:
            return page.infobox['name'].value
        except KeyError:
            pass
    return name
