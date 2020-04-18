"""
Artist wiki pages.

:author: Doug Skrypa
"""

import logging
from collections import defaultdict
from itertools import chain
from typing import MutableSet, List, Optional, Union

from ordered_set import OrderedSet

from ds_tools.compat import cached_property
from ..text import Name
from .base import PersonOrGroup
from .discography import DiscographyEntryFinder, DiscographyMixin

__all__ = ['Artist', 'Singer', 'Group']
log = logging.getLogger(__name__)


class Artist(PersonOrGroup, DiscographyMixin):
    _categories = ()

    def __repr__(self):
        return f'<{self.__class__.__name__}({self.name.artist_str()!r})[pages: {len(self._pages)}]>'

    @cached_property
    def name(self) -> Name:
        if not (names := self.names):
            raise AttributeError(f'This {self.__class__.__name__} has no \'name\' attribute')
        elif len(names) == 1:
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
        names = OrderedSet()                                                # type: MutableSet[Name]
        for artist_page, parser in self.page_parsers('parse_artist_name'):
            # log.debug(f'Processing names from {artist_page}')
            for name in parser.parse_artist_name(artist_page):
                # log.debug(f'Found name from {artist_page}: {name}')
                for _name in names:
                    if _name.is_compatible_with(name):
                        # log.debug(f'Combining {_name} with {name}')
                        _name += name
                        break
                else:
                    names.add(name)

        if not names:
            names.add(Name.from_enclosed(self._name))
        return names

    def _finder_with_entries(self) -> DiscographyEntryFinder:
        finder = DiscographyEntryFinder()
        for artist_page, parser in self.page_parsers('process_disco_sections'):
            parser.process_disco_sections(artist_page, finder)
        return finder


class Singer(Artist):
    _categories = ('singer', 'actor', 'actress', 'member', 'rapper', 'lyricist')

    @cached_property
    def groups(self) -> List['Group']:
        links = set(chain.from_iterable(
            parser.parse_member_of(page) for page, parser in self.page_parsers('parse_member_of')
        ))
        log.debug(f'Found group links for {self}: {links}')
        return list(Group.from_links(links).values())


class Group(Artist):
    _categories = ('group',)
    _not_categories = ('group processes', 'belief', 'single')

    @cached_property
    def members(self) -> Optional[List[Singer]]:
        for page, parser in self.page_parsers('parse_group_members'):
            members_dict = parser.parse_group_members(page)
            names = set(chain.from_iterable((titles for key, titles in members_dict.items() if titles != 'sub_units')))
            singers = Singer.from_titles(names, sites=page.site, search=False, strict=0)
            return list(singers.values())
        return None

    @cached_property
    def sub_units(self) -> Optional[List['Group']]:
        for page, parser in self.page_parsers('parse_group_members'):
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
