"""
Artist wiki pages.

:author: Doug Skrypa
"""

import logging
from itertools import chain
from typing import MutableSet, List, Optional, Union

from ordered_set import OrderedSet

from ds_tools.compat import cached_property
from wiki_nodes import Link, String
from ..text import Name
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
        for artist_page, parser in self.page_parsers():
            names.update(parser.parse_artist_name(artist_page))
            # for name in parser.parse_artist_name(artist_page):
            #     names.add(name)

        if not names:
            names.add(Name.from_enclosed(self._name))
        return names

    def _finder_with_entries(self) -> DiscographyEntryFinder:
        finder = DiscographyEntryFinder()
        for artist_page, parser in self.page_parsers():
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
    _not_categories = ('group processes', 'belief', 'single')

    @cached_property
    def members(self) -> Optional[List[Singer]]:
        for page, parser in self.page_parsers():
            members_dict = parser.parse_group_members(page)
            names = set(chain.from_iterable((titles for key, titles in members_dict.items() if titles != 'sub_units')))
            singers = Singer.from_titles(names, sites=page.site, search=False, strict=0)
            return list(singers.values())
        return None

    @cached_property
    def sub_units(self) -> Optional[List['Group']]:
        for page, parser in self.page_parsers():
            members_dict = parser.parse_group_members(page)
            if sub_units := members_dict.get('sub_units'):
                groups = Group.from_titles(sub_units, sites=page.site, search=False, strict=0)
                return list(groups.values())
        return None

    def _find_member(self, mem_type: str, name: Union[Name, str]) -> Union[Singer, 'Group', None]:
        if members := getattr(self, mem_type + 's'):
            for member in members:
                log.debug(f'Comparing {mem_type}={member} to {name=}')
                if member.name.matches(name):
                    log.debug(f'Found {mem_type}={member} == {name=!r}', extra={'color': 10})
                    return member
        return None

    def find_member(self, name: Union[Name, str]) -> Optional[Singer]:
        return self._find_member('member', name)

    def find_sub_unit(self, name: Union[Name, str]) -> Optional['Group']:
        return self._find_member('sub_unit', name)
