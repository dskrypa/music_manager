"""
Artist wiki pages.

:author: Doug Skrypa
"""

import logging
from itertools import chain
from typing import MutableSet, List, Optional, Union, Set, Iterator

from ordered_set import OrderedSet

from ds_tools.compat import cached_property
from ..text import Name
from .album import DiscographyEntry
from .base import PersonOrGroup, GROUP_CATEGORIES
from .discography import DiscographyEntryFinder, DiscographyMixin
from .parsing.utils import LANGUAGES

__all__ = ['Artist', 'Singer', 'Group']
log = logging.getLogger(__name__)


class Artist(PersonOrGroup, DiscographyMixin):
    _categories = ()

    def __repr__(self):
        return f'<{self.__class__.__name__}({self.name.artist_str()!r})[pages: {len(self._pages)}]>'

    def __lt__(self, other):
        return self.name < other.name

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
            try:
                for name in parser.parse_artist_name(artist_page):
                    # log.debug(f'Found name from {artist_page}: {name.full_repr()}')
                    for _name in names:
                        if _name.should_merge(name):
                            # log.debug(f'Combining {_name.full_repr()} with {name.full_repr()}')
                            _name += name
                            break
                    else:
                        # log.debug(f'Adding new name: {name.full_repr()}')
                        names.add(name)
            except Exception as e:
                log.error(f'Error processing names on {artist_page=}: {e}', exc_info=True)

        if not names:
            names.add(Name.from_enclosed(self._name))
        return names

    def _finder_with_entries(self) -> DiscographyEntryFinder:
        finder = DiscographyEntryFinder(self)
        for artist_page, parser in self.page_parsers('process_disco_sections'):
            parser.process_disco_sections(artist_page, finder)
        return finder

    @cached_property
    def languages(self) -> Set[str]:
        categories = set(chain.from_iterable(cat.split() for page in self.pages for cat in page.categories))
        langs = set(filter(None, (LANGUAGES.get(cat) for cat in categories)))
        if any(val in self._pages for val in ('kpop.fandom.com', 'kindie.fandom.com')):
            langs.add('Korean')
        return langs

    @cached_property
    def language(self) -> Optional[str]:
        if langs := self.languages:
            if len(langs) == 1:
                return next(iter(langs))
        log.debug(f'Unable to determine primary language for {self} - found {langs=}')
        return None


class Singer(Artist):
    _categories = ('singer', 'actor', 'actress', 'member', 'rapper', 'lyricist')
    _not_categories = ('groups', 'record labels')

    @cached_property
    def groups(self) -> List['Group']:
        links = set(chain.from_iterable(
            parser.parse_member_of(page) for page, parser in self.page_parsers('parse_member_of')
        ))
        log.debug(f'Found group links for {self}: {links}')
        return sorted(Group.from_links(links).values())


class Group(Artist):
    _categories = GROUP_CATEGORIES
    _not_categories = ('group processes', 'belief', 'single')

    @cached_property
    def members(self) -> Optional[List[Singer]]:
        for page, parser in self.page_parsers('parse_group_members'):
            members_dict = parser.parse_group_members(page)
            names = set(chain.from_iterable((titles for key, titles in members_dict.items() if titles != 'sub_units')))
            singers = Singer.from_titles(names, sites=page.site, search=False, strict=0)
            return sorted(singers.values())
        return None

    @cached_property
    def sub_units(self) -> Optional[List['Group']]:
        for page, parser in self.page_parsers('parse_group_members'):
            members_dict = parser.parse_group_members(page)
            if sub_units := members_dict.get('sub_units'):
                groups = Group.from_titles(sub_units, sites=page.site, search=False, strict=0)
                return sorted(groups.values())
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
