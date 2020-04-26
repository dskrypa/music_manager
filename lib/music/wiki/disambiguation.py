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
        page: WikiPage, client: MediaWikiClient, candidates: Candidates, existing: Optional[WE] = None,
        name: Optional[Name] = None, prompt=True
) -> Tuple[Type[WE], WikiPage]:
    """
    Given a disambiguation page and the pages it links to that match the chosen WikiEntity subclass, filter candidates
    based on the name of an existing WikiEntity and/or the original Name for which a search was performed.

    :param WikiPage page: A disambiguation page
    :param MediaWikiClient client: The wiki http client for the disambiguation page being processed
    :param candidates: Mapping of {Link: (WikiEntity subclass, WikiPage)}
    :param WikiEntity existing: An existing WikiEntity representing the same actual entity as the intended page that
      should be found; used to filter links/candidates.
    :param Name name: The Name that was searched for
    :param bool prompt: Prompt to interactively resolve ambiguous candidates after filtering
    :return tuple: Tuple of (WikiEntity subclass, WikiPage)
    """
    # log.debug(f'handle_disambiguation_candidates({page=}, len(candidates)={len(candidates)}, {existing=}, {name=})')
    if len(candidates) == 1:
        cat_cls, resolved_page = next(iter(candidates.values()))
        log.debug(f'Resolved ambiguous page={page} -> {resolved_page}')
        return cat_cls, resolved_page
    elif existing and candidates:
        matches = _filtered_candidates(existing.name, candidates, existing)
        # log.debug(f'Using {existing=}, filtered {candidates=} to {matches=}')
        return handle_disambiguation_candidates(page, client, matches, name=name, prompt=prompt)
    elif name and candidates:
        matches = _filtered_candidates(name, candidates, existing)
        # log.debug(f'Using {name=}, filtered {candidates=} to {matches=}')
        if len(matches) > 1 and name.english and name.non_eng:
            name = Name(non_eng=name.non_eng)
            matches = _filtered_candidates(name, candidates, existing)
            # log.debug(f'Using {name=}, filtered {candidates=} to {matches=}')
        return handle_disambiguation_candidates(page, client, matches, prompt=prompt)
    elif not candidates or not prompt:
        raise AmbiguousPageError(page_name(page), page, list(candidates))
    else:
        p_name = page_name(page)
        links = list(candidates)
        links.append('[None - skip]')
        # log.debug(f'Ambiguous title={p_name!r} on site={client.host} has too many candidates: {len(candidates)}')
        source = f'for ambiguous title={p_name!r} on {client.host}'
        choice = choose_item(links, 'link', source, before=f'\nFound multiple candidate links {source}:')
        if choice == '[None - skip]':
            raise AmbiguousPageError(page_name(page), page, list(candidates))
        return candidates[choice]


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
        log.debug(f'No disambiguation entry matches found for {existing or name!r}')
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
