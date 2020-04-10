"""
Artist wiki pages.

:author: Doug Skrypa
"""

import logging
from typing import MutableSet

from ordered_set import OrderedSet

from ds_tools.compat import cached_property
from wiki_nodes.http import MediaWikiClient
from wiki_nodes.nodes import Table, List, Link, String, CompoundNode
from ..text.name import Name
from .base import PersonOrGroup
from .discography import DiscographyEntryFinder, DiscographyMixin

__all__ = ['Artist', 'Singer', 'Group']
log = logging.getLogger(__name__)


class Artist(PersonOrGroup, DiscographyMixin):
    _categories = ()

    @cached_property
    def name(self) -> Name:
        names = self.names
        if not names:
            raise AttributeError(f'This {self.__class__.__name__} has no \'name\' attribute')
        if len(names) == 1:
            return next(iter(names))
        _name = self._name.lower()
        candidate = None
        for name in names:
            if _name in (name.eng_lower, name.non_eng):
                if name.english and name.non_eng:
                    return name
                else:
                    candidate = name
        return candidate or next(iter(names))

    @cached_property
    def names(self) -> MutableSet[Name]:
        names = OrderedSet()
        for site, artist_page in self._pages.items():
            try:
                parser = WikiParser.for_site(site)
            except KeyError:
                log.debug(f'No name extraction is configured for {artist_page}')
            else:
                names.update(parser.parse_artist_name(artist_page))
                # for name in parser.parse_artist_name(artist_page):
                #     names.add(name)

        if not names:
            names.add(Name(self._name))
        return names

    def _finder_with_entries(self) -> DiscographyEntryFinder:
        finder = DiscographyEntryFinder()
        for site, artist_page in self._pages.items():
            try:
                parser = WikiParser.for_site(site)
            except KeyError:
                log.debug(f'No discography entry extraction is configured for {artist_page}')
            else:
                parser.process_disco_sections(artist_page, finder)
        return finder


class Singer(Artist):
    _categories = ('singer', 'actor', 'actress', 'member', 'rapper')

    @cached_property
    def groups(self):
        groups = []
        for site, page in self._pages.items():
            if site == 'kpop.fandom.com':
                pass
            elif site == 'en.wikipedia.org':
                pass
            elif site == 'www.generasia.com':
                # group_list = page.sections['Profile'].content.as_mapping()['Groups']
                links = []
                member_str_index = None
                for i, node in enumerate(page.intro):
                    if isinstance(node, String) and 'is a member of' in node.value:
                        member_str_index = i
                    elif member_str_index is not None:
                        if isinstance(node, Link):
                            links.append(node)
                        if i - member_str_index > 3:
                            break

                if links:
                    groups.append(Artist.find_from_links(links))
            elif site == 'wiki.d-addicts.com':
                pass
            else:
                log.debug(f'No groups extraction is configured for {page}')

        return groups


class Group(Artist):
    _categories = ('group',)

    @cached_property
    def members(self):
        # TODO: Handle no links / incomplete links
        for site, page in self._pages.items():
            try:
                content = page.sections.find('Members').content
            except (KeyError, AttributeError):
                continue

            if type(content) is CompoundNode:
                for node in content:
                    if isinstance(node, (Table, List)):
                        content = node
                        break

            titles = []
            if isinstance(content, Table):
                for row in content:
                    if name := row.get('Name', row.get('name')):
                        if isinstance(name, Link):
                            titles.append(name.title)
                        elif isinstance(name, String):
                            titles.append(name.value)
                        else:
                            log.warning(f'Unexpected name type: {name!r}')
            elif isinstance(content, List):
                for entry in content.iter_flat():
                    if isinstance(entry, Link):
                        titles.append(entry.title)
                    elif isinstance(entry, CompoundNode):
                        if link := next(entry.find_all(Link, True), None):
                            titles.append(link.title)
                    elif isinstance(entry, String):
                        titles.append(entry.value)
                    else:
                        log.warning(f'Unexpected name type: {entry!r}')

            if titles:
                pages = MediaWikiClient(site).get_pages(titles)
                return [Singer.from_page(member) for member in pages.values()]
        return []

    @cached_property
    def sub_units(self):
        # TODO: implement
        return None


# Down here due to circular dependency
from .parsing import WikiParser
