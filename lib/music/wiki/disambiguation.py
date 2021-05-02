"""
:author: Doug Skrypa
"""

import json
import logging
from pathlib import Path
from typing import Type, Optional, Tuple, List, Iterator

from ds_tools.fs.paths import get_user_cache_dir
from wiki_nodes import MediaWikiClient, WikiPage, Link, CompoundNode, List as ListNode, Section
from ..common.prompts import choose_item
from ..text.name import Name
from .exceptions import AmbiguousPageError
from .typing import WE, Candidates
from .utils import page_name

__all__ = ['disambiguation_links', 'handle_disambiguation_candidates']
log = logging.getLogger(__name__)


def handle_disambiguation_candidates(
    page: WikiPage,
    client: MediaWikiClient,
    candidates: Candidates,
    existing: Optional[WE] = None,
    name: Optional[Name] = None,
    prompt=True,
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
    # log.debug(f'handle_disambiguation_candidates({page=}, len(candidates)={len(candidates)}, {existing=}, {name=})', extra={'color': 13}, stack_info=True)
    if len(candidates) == 1:
        cat_cls, resolved_page = next(iter(candidates.values()))
        # log.debug(f'Resolved ambiguous page={page} -> {resolved_page}', stack_info=True)
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
        if _should_skip(p_name, links):
            choice = '[None - skip]'
        else:
            links.append('[None - skip]')
            links.append('[None - skip & remember]')
            # log.debug(f'Ambiguous title={p_name!r} on site={client.host} has too many candidates: {len(candidates)}')
            source = f'for ambiguous title={p_name!r} on {client.host}'
            choice = choose_item(links, 'link', source, before=f'\nFound multiple candidate links {source}:')

        if choice == '[None - skip & remember]':
            _always_skip(p_name, links[:-2])  # noqa
            choice = '[None - skip]'
        if choice in ('[None - skip]', None):
            raise AmbiguousPageError(page_name(page), page, list(candidates))

        return candidates[choice]


def _should_skip(p_name: str, links: Candidates) -> bool:
    key = str(sorted(links))
    skip_dir = Path(get_user_cache_dir('music_manager/disambiguation_skip'))
    skip_path = skip_dir.joinpath(f'{p_name}.json')
    if skip_path.exists():
        with skip_path.open('r') as f:
            try:
                return json.load(f)[key]
            except KeyError:
                return False
    return False


def _always_skip(p_name: str, links: Candidates):
    key = str(sorted(links))
    skip_dir = Path(get_user_cache_dir('music_manager/disambiguation_skip'))
    skip_path = skip_dir.joinpath(f'{p_name}.json')
    if skip_path.exists():
        with skip_path.open('r') as f:
            data = json.load(f)
    else:
        data = {}

    data[key] = True
    with skip_path.open('w') as f:
        json.dump(data, f, sort_keys=True, indent=4)


def _filtered_candidates(name: Name, candidates: Candidates, existing: Optional[WE] = None) -> Candidates:
    matches = {}
    groups = getattr(existing, 'groups', None)
    group_names = [group.name for group in groups] if groups else None
    for link, (cat_cls, _page) in candidates.items():
        try:
            candidate = cat_cls(page_name(_page), _page)
            po_name = candidate.name
        except Exception:
            pass
        else:
            if name.matches(po_name):
                if existing:
                    log.debug(f'Matched disambiguation entry={_page} / {po_name!r} to {existing} / {name!r}')
                    if group_names and not link.title.lower().startswith('category:'):
                        # log.debug(f'Checking groups for {link=!r}')
                        try:
                            cand_groups = candidate.groups
                        except Exception:
                            pass
                        else:
                            if cand_groups and not any(cg.name.matches_any(group_names) for cg in cand_groups):
                                log.debug(
                                    f'Filtering out disambiguation entry={_page} / {po_name!r} for {existing} / '
                                    f'{name!r} due to group membership mismatch'
                                )
                                continue
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
