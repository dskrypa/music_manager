"""
:author: Doug Skrypa
"""

import logging
from typing import Type, Optional, Tuple, List, Iterator

from ds_tools.input import choose_item
from wiki_nodes import MediaWikiClient, WikiPage, Link, CompoundNode, List as ListNode, Section
from ..text import Name
from .exceptions import AmbiguousPageError
from .typing import WE, Candidates
from .utils import page_name

__all__ = ['disambiguation_links', 'handle_disambiguation_candidates']
log = logging.getLogger(__name__)


def handle_disambiguation_candidates(
        page: WikiPage, client: MediaWikiClient, links: Optional[List[Link]], candidates: Candidates,
        existing: Optional[WE] = None, name: Optional[Name] = None, prompt=True
) -> Tuple[Type[WE], WikiPage]:
    if len(candidates) == 1:
        cat_cls, resolved_page = next(iter(candidates.values()))
        log.debug(f'Resolved ambiguous page={page} -> {resolved_page}')
        return cat_cls, resolved_page
    elif not candidates or (not existing and not prompt):
        raise AmbiguousPageError(page_name(page), page, links)
    elif existing:
        matches = _filtered_candidates(existing.name, candidates, existing)
        return handle_disambiguation_candidates(page, client, links, matches, name=name, prompt=prompt)
    elif name:
        matches = _filtered_candidates(existing.name, candidates, existing)
        return handle_disambiguation_candidates(page, client, links, matches, prompt=prompt)
    else:
        p_name = page_name(page)
        links = list(candidates)
        log.debug(f'Ambiguous title={p_name!r} on site={client.host} has too many candidates: {len(candidates)}')
        source = f'for ambiguous title={p_name!r} on {client.host}'
        link = choose_item(links, 'link', source, before=f'\nFound multiple candidate links {source}:')
        return candidates[link]


def _filtered_candidates(name: Name, candidates: Candidates, existing: Optional[WE] = None) -> Candidates:
    matches = {}
    for link, (cat_cls, _page) in candidates.items():
        po_name = cat_cls(page_name(_page), _page).name
        if name.matches(po_name):
            if existing:
                log.debug(f'Matched disambiguation entry={_page} / {po_name!r} to {existing} / {name!r}')
            else:
                log.debug(f'Matched disambiguation entry={_page} / {po_name!r} to {name!r}')
            matches[link] = (cat_cls, _page)
    if not matches:
        log.debug(f'No disambiguation entry matches found for {existing or name}')
    return matches


def disambiguation_links(page: WikiPage) -> List[Link]:
    links = []
    for section in page:
        try:
            for link in _disambiguation_links(section):
                if link.title and 'disambiguation' not in link.title:
                    links.append(link)
        except Exception as e:
            raise ValueError(f'Unexpected section content on {page=} in {section=}') from e
        # raise ValueError(f'Unexpected section content on {page=} in {section=}:\n{content.pformat()}')
    return links


def _disambiguation_links(section: Section) -> Iterator[Link]:
    content = section.content
    if isinstance(content, ListNode):
        yield from _disambiguation_entries(content)
    elif isinstance(content, CompoundNode):
        for link_list in content.find_all(ListNode):
            yield from _disambiguation_entries(link_list)

    if section.children:
        for child in section:
            yield from _disambiguation_links(child)


def _disambiguation_entries(list_node: ListNode) -> Iterator[Link]:
    for entry in list_node.iter_flat():
        if isinstance(entry, Link):
            yield entry
        elif isinstance(entry, CompoundNode):
            if isinstance(entry[0], Link):
                yield entry[0]
