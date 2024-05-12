"""
A WikiEntity represents an entity that is represented by a page in one or more MediaWiki sites.

:author: Doug Skrypa
"""

from __future__ import annotations

import logging
from collections import defaultdict, Counter
from itertools import chain
from typing import Iterable, Optional, Union, Iterator, Type, Collection, Mapping, MutableMapping

from ds_tools.caching.decorators import ClearableCachedPropertyMixin, cached_property
from wiki_nodes import MediaWikiClient, WikiPage, Link, MappingNode, Template, PageMissingError

from ..text.name import Name
from .disambiguation import disambiguation_links, handle_disambiguation_candidates
from .disco_entry import DiscoEntry
from .exceptions import EntityTypeError, NoPagesFoundError, AmbiguousPageError, AmbiguousPagesError
from .exceptions import NoLinkedPagesFoundError
from .typing import WE, Pages, PageEntry, StrOrStrs
from .utils import site_titles_map, page_name, titles_and_title_name_map, multi_site_page_map

__all__ = ['WikiEntity', 'PersonOrGroup', 'Agency', 'SpecialEvent', 'TVSeries', 'TemplateEntity', 'EntertainmentEntity']
log = logging.getLogger(__name__)
DEFAULT_WIKIS = ['kpop.fandom.com', 'www.generasia.com', 'wiki.d-addicts.com', 'en.wikipedia.org']
GROUP_CATEGORIES = ('group', 'subunits', 'duos')
SINGER_CATEGORIES = (
    'singer', 'actor', 'actress', 'member', 'rapper', 'lyricist', 'pianist', 'songwriter', 'births', 'male', 'kcomposer'
)
WikiPage._ignore_category_prefixes = ('album chart usages for', 'discography article stubs')


class WikiEntity(ClearableCachedPropertyMixin):
    __slots__ = ('_name', '_pages', '__name')
    _categories: tuple[str, ...] = ()
    _not_categories: tuple[str, ...] = ()
    _category_classes: dict[str, Type[WE]] = {}
    _subclasses = {}
    _name: str
    _pages: MutableMapping[str, WikiPage]

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        for cat in cls._categories:
            WikiEntity._category_classes[cat] = cls
        for base_cls, sub_classes in WikiEntity._subclasses.items():
            if isinstance(cls, base_cls):
                sub_classes.add(cls)
        WikiEntity._subclasses[cls] = set()

    def __init__(self, name: Optional[str], pages: Pages = None):
        """
        :param name: The name of this entity
        :param pages: One or more WikiPage objects
        """
        if name is not None and not isinstance(name, str):
            raise TypeError(f'Unexpected {name=} with {pages=}')
        self._name = name
        if isinstance(pages, MutableMapping):
            self._pages = pages
        elif pages:
            if isinstance(pages, str):
                raise TypeError(f'pages must be a WikiPage, or dict of site:WikiPage, or list of WikiPage objs')
            try:
                self._pages = {page.site: page for page in pages}  # noqa
            except (TypeError, AttributeError):
                if isinstance(pages, WikiPage):
                    self._pages = {pages.site: pages}
                else:
                    raise ValueError(f'{self.__class__.__name__}: Unexpected value for {pages=}') from None
        else:
            self._pages = {}

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__}({self.name!r})[pages: {len(self._pages)}]>'

    @property
    def name(self) -> Name:
        try:
            return self.__name
        except AttributeError:
            self.__name = name = Name.from_enclosed(self._name)  # noqa
            return name

    def _add_page(self, page: WikiPage):
        self._pages[page.site] = page
        self.clear_cached_properties()

    def _add_pages(self, pages: Mapping[str, WikiPage]):
        self._pages.update(pages)
        self.clear_cached_properties()

    @property
    def first_page(self) -> WikiPage:
        return next(iter(self._pages.values()))

    @property
    def pages(self) -> Iterator[WikiPage]:
        yield from self._pages.values()

    def page_parsers(self, method: str = None) -> Iterator[tuple[WikiPage, WikiParser]]:
        for site, page in sorted(self._pages.items(), key=_site_page_key):
            if parser := WikiParser.for_site(site, method):
                yield page, parser
            else:
                log.log(9, f'No parser is configured for {page}')

    @classmethod
    def _validate(
        cls: Type[WE],
        obj: PageEntry,
        existing: WE = None,
        name: Name = None,
        prompt: bool = True,
        visited: set[Link] = None,
    ) -> tuple[Type[WE], PageEntry]:
        """
        :param WikiPage|DiscoEntry obj: A WikiPage or DiscoEntry to be validated against this class's categories
        :param WikiEntity existing: An existing WikiEntity that the given page/entry will be added to; used to filter
          disambiguation page links, if the given page is a disambiguation page
        :param Name name: A Name to use during disambiguation page resolution
        :param bool prompt: Attempt to interactively resolve disambiguation pages if unable to do so automatically
        :param visited: A set of links that have already been visited for disambiguation resolution
        :return tuple: Tuple of (WikiEntity subclass, page/entry)
        """
        if visited is None:
            visited = set()

        if isinstance(obj, WikiPage):
            if obj.is_disambiguation:
                visited.add(obj.as_link)
                log.debug(f'{cls.__name__}._validate found a disambiguation page: {obj}')
                return cls._resolve_ambiguous(obj, existing, name, prompt, visited)
            elif obj.is_template:
                if cls in (WikiEntity, TemplateEntity):
                    return TemplateEntity, obj
                raise EntityTypeError(f'{obj} is a Template page, which is not compatible with {cls.__name__}')

        if cat_cls := EntityClassifier(obj, cls).get_class():
            log.debug(f'Classified {obj} as {cat_cls=}')
            return cat_cls, obj
        elif cls is not WikiEntity:
            # No match was found; only WikiEntity is allowed to be instantiated directly with no matching categories
            if isinstance(obj, WikiPage) and (obj.disambiguation_link or obj.similar_name_link):
                log.debug(f'{cls.__name__}._validate found a possible disambiguation link from: {obj}')
                link = obj.disambiguation_link or obj.similar_name_link
                if link not in visited:
                    try:
                        return cls._handle_disambiguation_link(link, existing, name, prompt, visited)
                    except PageMissingError as e:
                        log.debug(f'The disambiguation link was not found: {e}')
            raise EntityTypeError(
                f'{obj} has no categories that make it a {cls.__name__} or subclass thereof'
                f' - page categories: {obj.categories}'
            )

        return cls, obj

    # region Disambiguation

    @classmethod
    def _handle_disambiguation_link(
        cls, link: Link, existing: Optional[WE], name: Optional[Name], prompt, visited: set[Link] = None
    ) -> tuple[Type[WE], PageEntry]:
        if visited is None:
            visited = set()
        visited.add(link)
        mw_client, title = link.client_and_title
        return cls._validate(mw_client.get_page(title), existing, name, prompt, visited)

    @classmethod
    def _resolve_ambiguous(
        cls: Type[WE],
        page: WikiPage,
        existing: WE = None,
        name: Name = None,
        prompt: bool = True,
        visited: set[Link] = None,
    ) -> tuple[Type[WE], WikiPage]:
        """
        :param page: A disambiguation page
        :param existing: An existing WikiEntity that the resolved page will be added to; used to filter disambiguation
          page links
        :param name: A Name to match, if no existing WikiEntity exists or if its parsed name is insufficient to filter
          results
        :param prompt: Attempt to interactively resolve disambiguation pages if unable to do so automatically
        :return: Tuple of (WikiEntity subclass, WikiPage)
        """
        if not (links := disambiguation_links(page)):
            raise AmbiguousPageError(page_name(page), page, links)

        client, title_link_map = next(iter(site_titles_map(links).items()))     # type: MediaWikiClient, dict[str, Link]
        candidates = {}
        for title, _page in client.get_pages(title_link_map).items():
            link = title_link_map[title]
            if _page.title != link.title:  # In case of redirects
                link = Link(f'[[{_page.title}]]', link.root)
            if not visited or _page.as_link not in visited:
                try:
                    candidates[link] = cls._validate(_page, visited=visited)
                except EntityTypeError:
                    pass

        return handle_disambiguation_candidates(page, client, candidates, existing, name, prompt)

    # endregion

    # region Alternate Constructors

    @classmethod
    def _by_category(cls: Type[WE], obj: PageEntry, name: Name = None, *args, **kwargs) -> WE:
        cat_cls, obj = cls._validate(obj, name=name)
        if isinstance(obj, DiscoEntry):
            entity_name, page = obj.title, None
        else:
            entity_name, page = page_name(obj), obj
        return cat_cls(entity_name, page, *args, **kwargs)

    @classmethod
    def from_page(cls: Type[WE], page: WikiPage, *args, **kwargs) -> WE:
        return cls._by_category(page, *args, **kwargs)

    @classmethod
    def _from_multi_site_pages(
        cls: Type[WE], pages: Collection[WikiPage], name: Name = None, strict: int = 2, entity: WE = None, **kwargs
    ) -> WE:
        # log.debug(f'Processing {len(pages)} multi-site pages')
        page_link_map = {}
        type_errors = 0
        _name = name
        for page in sorted(pages):      # Sort so disambiguation pages are handled after proper matches
            try:
                cat_cls, page = cls._validate(page, entity, name)
            except AmbiguousPageError as e:
                page_link_map[page] = e.links
                _name = _name or page_name(page)
            except EntityTypeError as e:
                if strict > 1:
                    raise
                else:
                    _name = _name or page_name(page)
                    type_errors += 1
                    log.log(logging.WARNING if strict else logging.DEBUG, e, extra={'color': 9})
            else:
                if entity is None:
                    entity = cat_cls(page_name(page), page, **kwargs)
                else:
                    entity._add_page(page)

        if entity is None:
            name = _name
            if page_link_map:
                raise AmbiguousPagesError(name, page_link_map)
            elif type_errors:
                raise EntityTypeError(f'Encountered {type_errors} type errors and found no valid pages for {name=}')
            else:
                raise ValueError(f'No pages found for {name=}')
        else:
            if page_link_map:
                lvl = logging.WARNING if strict else logging.DEBUG
                for page, links in page_link_map.items():
                    log.log(lvl, AmbiguousPageError(page_name(page), page, links))
            return entity

    @classmethod
    def from_title(
        cls: Type[WE],
        title: str,
        sites: StrOrStrs = None,
        search: bool = True,
        research: bool = False,
        name: Name = None,
        strict: int = 2,
        **kwargs,
    ) -> WE:
        """
        :param title: A page title
        :param sites: A list or other iterable that yields site host strings
        :param search: Whether the provided title should also be searched for, in case there is not an exact match.
        :param research: If only one site returned a hit, re-search with the title from that site
        :param name: The Name of the entity to retrieve
        :param strict: Error handling strictness.  If 2 (default), let all exceptions be propagated.  If 1, log
          EntityTypeError and AmbiguousPageError as a warning.  If 0, log those errors on debug level.
        :return: A WikiEntity (or subclass thereof) that represents the page(s) with the given title.
        """
        sites = _sites(sites)
        pages, errors = MediaWikiClient.get_multi_site_page(title, sites, search=search)
        if not pages:
            raise NoPagesFoundError(f'No pages found for {title=} from any of these sites: {", ".join(sites)}')

        entity = cls._from_multi_site_pages(pages.values(), name, strict=strict, **kwargs)
        if search and research and 0 < len(entity._pages) < len(sites):
            if (name := entity.name) and (eng := name.english) and eng != title:  # noqa
                log.debug(f'Returning {cls.__name__}.from_title for {eng=}')
                research_entity = cls.from_title(eng, set(sites).difference(entity._pages), search, False, **kwargs)
                research_entity._add_pages(entity._pages)
                return research_entity

        return entity

    @classmethod
    def from_titles(
        cls: Type[WE],
        titles: Iterable[Union[str, Name]],
        sites: StrOrStrs = None,
        search: bool = True,
        strict: int = 2,
        research: bool = False,
    ) -> dict[Union[str, Name], WE]:
        """
        :param titles: Page titles to retrieve
        :param sites: Sites from which to retrieve them
        :param search: Resolve titles that may not be exact matches
        :param strict: Error handling strictness.  If 2 (default), let all exceptions be propagated.  If 1, log
          EntityTypeError and AmbiguousPageError as a warning.  If 0, log those errors on debug level.
        :param research: If only one site returned a hit for a given title, re-search with the title from that site
        :return: Mapping of {title: WikiEntity} for the given titles
        """
        titles, title_name_map = titles_and_title_name_map(titles)
        # log.debug(f'{title_name_map=}')
        sites = _sites(sites)
        query_map = {site: titles for site in sites}
        # log.debug(f'Retrieving {cls.__name__}s: {query_map}', extra={'color': 14})
        log.debug(f'Retrieving {cls.__name__}s from sites={sorted(query_map)} with {titles=}')
        title_entity_map = cls._from_site_title_map(query_map, search, strict, title_name_map)
        if not (search and research):
            return title_entity_map

        research_query_map = defaultdict(list)
        research_title_name_map = {}
        new_orig_title_map = {}
        for title, entity in title_entity_map.items():
            if not (0 < len(entity._pages) < len(sites)):
                continue
            elif (name := entity.name) and (eng := name.english) and eng != title and eng not in title_name_map:  # noqa
                # log.debug(f'Will re-search for {eng=} {title=} {entity=}')
                new_orig_title_map[eng] = title
                research_title_name_map[eng] = title_name_map.get(title)
                for site in set(sites).difference(entity._pages).union({'kindie.fandom.com'}):
                    research_query_map[site].append(eng)

        if not title_entity_map:
            for title in set(chain(titles, title_name_map)):
                if title.upper() == title:
                    tc_title = title.title()
                    new_orig_title_map[tc_title] = title
                    research_title_name_map[tc_title] = title_name_map.get(title)
                    for site in sites:
                        research_query_map[site].append(tc_title)

        if research_query_map:
            log.debug(
                f'Re-attempting retrieval of {cls.__name__}s from sites={sorted(research_query_map)} with'
                f' titles={list(new_orig_title_map)}'
            )
            new_title_entity_map = cls._from_site_title_map(research_query_map, search, strict, research_title_name_map)
            for eng_or_name, entity in new_title_entity_map.items():
                # log.debug(f'Found re-search result for {eng=} {entity=}')
                orig_title = new_orig_title_map.get(eng_or_name, eng_or_name)
                try:
                    orig = title_entity_map[orig_title]
                except KeyError:
                    title_entity_map[orig_title] = entity
                else:
                    orig._add_pages(entity._pages)

        return title_entity_map

    @classmethod
    def _from_site_title_map(
        cls: Type[WE],
        site_title_map: Mapping[Union[str, MediaWikiClient], Iterable[str]],
        search: bool = False,
        strict: int = 2,
        title_name_map=None,
    ) -> dict[Union[str, Name], WE]:
        # log.debug(f'{cls.__name__}._from_site_title_map({site_title_map=},\n{search=}, {strict=},\n{title_name_map=})')
        if title_name_map is None:
            title_name_map = {}
        results, _errors = MediaWikiClient.get_multi_site_pages(site_title_map, search=search)
        for title, error in _errors.items():
            log.error(f'Error processing {title=}: {error}', extra={'color': 9})

        title_entity_map = {}
        for title, pages in multi_site_page_map(results).items():
            name = title_name_map.get(title)
            try:
                title_entity_map[name or title] = cls._from_multi_site_pages(pages, name, strict)
            except (EntityTypeError, AmbiguousPageError, AmbiguousPagesError) as e:
                if strict > 1:
                    raise
                else:
                    log.log(logging.WARNING if strict else logging.DEBUG, e, extra={'color': 9})

        return title_entity_map

    @classmethod
    def from_url(cls: Type[WE], url: str, **kwargs) -> WE:
        return cls._by_category(MediaWikiClient.page_for_article(url), **kwargs)

    @classmethod
    def from_link(cls: Type[WE], link: Link, **kwargs) -> WE:
        mw_client, title = link.client_and_title
        try:
            return cls._by_category(mw_client.get_page(title), **kwargs)
        except AmbiguousPageError as e:
            e.add_context(f'While processing {link=} from {link.root}')
            raise

    @classmethod
    def find_from_links(cls: Type[WE], links: Collection[Link]) -> WE:
        """
        :param links: An iterable that yields Link nodes.
        :return: The first instance of this class for a link with a valid category for this class or a subclass thereof.
        """
        last_exc = None
        client_title_link_map = site_titles_map(links)
        results, errors = MediaWikiClient.get_multi_site_pages(client_title_link_map)
        for site, pages in results.items():
            for title, page in pages.items():
                try:
                    return cls._by_category(page)
                except EntityTypeError as e:
                    last_exc = e
                except AmbiguousPageError as e:
                    link = client_title_link_map[page._client][title]
                    e.add_context(f'While processing {link=} from {link.root}')
                    # last_exc = e
                    raise

        if last_exc:
            raise last_exc
        raise NoLinkedPagesFoundError(links)

    @classmethod
    def from_links(cls: Type[WE], links: Iterable[Link], strict: int = 2) -> dict[Link, WE]:
        link_entity_map = {}
        client_title_link_map = site_titles_map(links)
        title_entity_map = cls._from_site_title_map(client_title_link_map, False, strict)
        for title, entity in title_entity_map.items():
            for site, page in entity._pages.items():
                # link = client_title_link_map[MediaWikiClient(site)][title]
                link = client_title_link_map[page._client][title]
                link_entity_map[link] = entity
        return link_entity_map

    # endregion


class EntityClassifier:
    __slots__ = ('obj', 'entity_cls', 'cls_score_map', 'good_matches', 'bad_matches', '_scores')
    _scores: list[tuple[int, Type[WE]]]

    def __init__(self, obj: PageEntry, entity_cls: Type[WE]):
        self.obj = obj
        self.entity_cls = entity_cls
        self.cls_score_map = Counter()
        self.good_matches = defaultdict(lambda: defaultdict(set))
        self.bad_matches = defaultdict(lambda: defaultdict(set))
        self._classify(obj, entity_cls)

    def _classify(self, obj: PageEntry, entity_cls: Type[WE]):
        cls_score_map, good_matches, bad_matches = self.cls_score_map, self.good_matches, self.bad_matches
        for page_cat in obj.categories:
            for cls_cat, cat_cls in entity_cls._category_classes.items():
                if cls_cat in page_cat:
                    good_matches[cat_cls][cls_cat].add(page_cat)
                    cls_score_map[cat_cls] += 1
                if bad_indicator := next((bci for bci in cat_cls._not_categories if bci in page_cat), None):
                    bad_matches[cat_cls][bad_indicator].add(page_cat)
                    cls_score_map[cat_cls] -= 1

    def get_scores(self) -> list[tuple[int, Type[WE]]]:
        try:
            return self._scores
        except AttributeError:
            # Can't sort using the classes themselves
            scores = sorted(((v, k.__name__, k) for k, v in self.cls_score_map.items()), reverse=True)
            self._scores = scores = [(v, k) for v, _, k in scores]  # noqa
            return scores  # noqa

    def get_details(self) -> str:
        lines = []
        for score, cat_cls in self.get_scores():
            lines.append(f' - {cat_cls.__name__} ({score}):')
            if good := self.good_matches[cat_cls]:
                categories = {k: sorted(v) for k, v in sorted(good.items())}
                lines.append(f'    - matching categories: {categories}')
            if bad := self.bad_matches[cat_cls]:
                categories = {k: sorted(v) for k, v in sorted(bad.items())}
                lines.append(f'    - counter-indicator categories: {categories}')

        return '\n'.join(lines)

    def get_class(self) -> Optional[Type[WE]]:
        if not (scores := self.get_scores()):
            return None

        for score, cat_cls in scores:
            if score > 0 and issubclass(cat_cls, self.entity_cls):  # True for this class and its subclasses
                return cat_cls

        details = self.get_details()
        raise EntityTypeError(
            f'{self.obj} is incompatible with {self.entity_cls.__name__} due to its categories - details:\n{details}'
        )


class EntertainmentEntity(WikiEntity):
    """An entity that may be related to the entertainment industry in some way.  Used to filter out irrelevant pages."""
    __slots__ = ()
    _categories = ()

    @classmethod
    def _validate(cls: Type[WE], obj: PageEntry, *args, **kwargs) -> tuple[Type[WE], PageEntry]:
        if isinstance(obj, WikiPage) and obj.title.lower().startswith('category:'):
            # log.error(f'{obj} is a Category page, which is not compatible with {cls.__name__}', stack_info=True)
            raise EntityTypeError(f'{obj} is a Category page, which is not compatible with {cls.__name__}')
        return super()._validate(obj, *args, **kwargs)


class PersonOrGroup(EntertainmentEntity):
    __slots__ = ()
    _categories = ()

    @classmethod
    def from_name(cls: Type[WE], name, affiliations=None, sites=None) -> WE:
        """
        :param str name: The name of a person or group
        :param iterable affiliations: A list or other iterable that yields name strings and/or WikiEntity objects that
          are associated with the PersonOrGroup with the given name.  When name strings are provided, they may be
          matched against a broader range of things that this PersonOrGroup may be associated with; i.e., if an
          :class:`Agency` object is provided, then a PersonOrGroup who is or was in that agency would match, but if that
          agency's name was provided as a string affiliation, then it will be compared to other fields as well.
        :param iterable sites: A list or other iterable that yields site host strings
        :return: The PersonOrGroup (or subclass thereof) matching the given criteria
        """
        pass    # TODO: implement


class Agency(PersonOrGroup):
    __slots__ = ()
    _categories = ('agency', 'agencies', 'record label')


class SpecialEvent(EntertainmentEntity):
    __slots__ = ()
    _categories = ('competition',)


class TVSeries(EntertainmentEntity):
    __slots__ = ()
    _categories = ('television program', 'television series', 'drama', 'survival show', 'music shows')

    def soundtrack_links(self) -> list[Link]:
        links = []
        for page, parser in self.page_parsers('parse_soundtrack_links'):
            links.extend(parser.parse_soundtrack_links(page))
        return links


class TemplateEntity(WikiEntity):
    _categories = ()

    @classmethod
    def from_name(cls, name: str, site: str) -> TemplateEntity:
        page = MediaWikiClient(site).get_page(f'Template:{name}')
        return cls._by_category(page)

    @cached_property
    def group(self):
        page_content = next(iter(self.pages)).sections.content
        if isinstance(page_content, Template) and isinstance(page_content.value, MappingNode):
            if (title := page_content.value.get('title')) and isinstance(title, Link):
                entity = WikiEntity.from_link(title)
                if entity._categories == GROUP_CATEGORIES:  # Since Group can't be imported here
                    return entity
        return None


def _sites(sites: StrOrStrs) -> list[str]:
    if isinstance(sites, str):
        sites = [sites]
    return sites or DEFAULT_WIKIS


def _site_page_key(site_page):
    site, page = site_page
    if 'fandom' in site:
        return 0, site, page
    try:
        index = DEFAULT_WIKIS.index(site)
    except ValueError:
        index = len(DEFAULT_WIKIS)
    return index, site, page


# Down here due to (non-obvious) circular dependency
from .parsing import WikiParser  # noqa
