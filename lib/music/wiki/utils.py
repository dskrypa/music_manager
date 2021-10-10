"""
:author: Doug Skrypa
"""

import logging
from collections import defaultdict
from typing import Iterable, Union

from wiki_nodes import MediaWikiClient, WikiPage, Link, String
from ..text.name import Name

__all__ = ['site_titles_map', 'page_name', 'titles_and_title_name_map', 'multi_site_page_map', 'short_site']
log = logging.getLogger(__name__)


def site_titles_map(links: Iterable[Link]) -> dict[MediaWikiClient, dict[str, Link]]:
    site_map = defaultdict(dict)
    for link in links:
        mw_client, title = link.client_and_title
        site_map[mw_client][title] = link
    return site_map  # noqa


def multi_site_page_map(get_multi_site_pages_results) -> dict[str, list[WikiPage]]:
    title_page_map = defaultdict(list)
    for site, pages in get_multi_site_pages_results.items():
        log.debug(f'Found {len(pages)} pages from {site=!r}: {", ".join(sorted(pages))}')
        for title, page in pages.items():
            title_page_map[title].append(page)
    return title_page_map  # noqa


def page_name(page: WikiPage) -> str:
    name = page.title
    if page.infobox:
        try:
            ib_name = page.infobox['name']
        except KeyError:
            pass
        else:
            if isinstance(ib_name, String):
                return ib_name.value
    return name


def titles_and_title_name_map(titles: Iterable[Union[str, Name]]) -> tuple[list[str], dict[str, Name]]:
    title_name_map = {}
    _titles = []
    for title in titles:
        if isinstance(title, Name):
            if _title := title.english or title.non_eng:
                _titles.append(_title)
                title_name_map[_title] = title
            else:
                raise ValueError(f'Invalid {title=}')
        else:
            _titles.append(title)

    return sorted(_titles), title_name_map


def short_site(site: str) -> str:
    parts = site.split('.')[:-1]            # omit domain
    if parts[0] in {'www', 'wiki', 'en'}:   # omit common prefixes
        parts = parts[1:]
    return '.'.join(parts)
