"""
A WikiEntity represents an entity that is represented by a page in one or more MediaWiki sites.

:author: Doug Skrypa
"""

import logging
from typing import Iterable, Optional, Union, Dict, Iterator, Type, Tuple, List, Collection, Mapping

from ds_tools.compat import cached_property
from wiki_nodes import MediaWikiClient, WikiPage, Link, MappingNode, Template
from ..text import Name
from .disambiguation import disambiguation_links, handle_disambiguation_candidates
from .disco_entry import DiscoEntry
from .exceptions import EntityTypeError, NoPagesFoundError, AmbiguousPageError, AmbiguousPagesError
from .typing import WE, Pages, PageEntry, StrOrStrs
from .utils import site_titles_map, link_client_and_title, page_name, titles_and_title_name_map, multi_site_page_map

__all__ = ['WikiEntity', 'PersonOrGroup', 'Agency', 'SpecialEvent', 'TVSeries', 'TemplateEntity', 'EntertainmentEntity']
log = logging.getLogger(__name__)
DEFAULT_WIKIS = ['kpop.fandom.com', 'www.generasia.com', 'wiki.d-addicts.com', 'en.wikipedia.org']
GROUP_CATEGORIES = ('group', 'subunits')
WikiPage._ignore_category_prefixes = ('album chart usages for', 'discography article stubs')


class WikiEntity:
    _categories = ()
    _not_categories = ()
    _category_classes = {}
    _subclasses = {}

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
        :param str|None name: The name of this entity
        :param WikiPage|DiscoEntry|dict|iterable pages: One or more WikiPage objects
        """
        if name is not None and not isinstance(name, str):
            raise TypeError(f'Unexpected {name=!r} with {pages=}')
        self._name = name
        if isinstance(pages, Dict):
            self._pages = pages         # type: Dict[str, WikiPage]
        else:
            self._pages = {}            # type: Dict[str, WikiPage]
            if pages and not isinstance(pages, DiscoEntry):
                if isinstance(pages, str):
                    raise TypeError(f'pages must be a WikiPage, or dict of site:WikiPage, or list of WikiPage objs')
                elif isinstance(pages, WikiPage):
                    self._pages[pages.site] = pages
                elif isinstance(pages, Iterable):
                    for page in pages:
                        self._pages[page.site] = page
                else:
                    raise ValueError(f'Unexpected pages value: {pages!r}')

    def __repr__(self):
        return f'<{self.__class__.__name__}({self.name!r})[pages: {len(self._pages)}]>'

    @cached_property
    def name(self) -> Name:
        return Name.from_enclosed(self._name)

    def _add_page(self, page: WikiPage):
        self._pages[page.site] = page

    @property
    def pages(self) -> Iterator[WikiPage]:
        yield from self._pages.values()

    def page_parsers(self, method: Optional[str] = None) -> Iterator[Tuple[WikiPage, 'WikiParser']]:
        for site, page in self._pages.items():
            if parser := WikiParser.for_site(site, method):
                yield page, parser
            else:
                log.log(9, f'No parser is configured for {page}')

    @classmethod
    def _validate(
            cls: Type[WE], obj: PageEntry, existing: Optional[WE] = None, name: Optional[Name] = None, prompt=True
    ) -> Tuple[Type[WE], PageEntry]:
        """
        :param WikiPage|DiscoEntry obj: A WikiPage or DiscoEntry to be validated against this class's categories
        :param WikiEntity existing: An existing WikiEntity that the given page/entry will be added to; used to filter
          disambiguation page links, if the given page is a disambiguation page
        :param Name name: A Name to use during disambiguation page resolution
        :param bool prompt: Attempt to interactively resolve disambiguation pages if unable to do so automatically
        :return tuple: Tuple of (WikiEntity subclass, page/entry)
        """
        if isinstance(obj, WikiPage):
            if obj.is_disambiguation:
                log.debug(f'{cls.__name__}._validate found a disambiguation page: {obj}')
                return cls._resolve_ambiguous(obj, existing, name, prompt)
            elif obj.is_template:
                if cls in (WikiEntity, TemplateEntity):
                    return TemplateEntity, obj
                raise EntityTypeError(f'{obj} is a Template page, which is not compatible with {cls.__name__}')
        page_cats = obj.categories
        err_fmt = '{} is incompatible with {} due to category={{!r}} [{{!r}}]'.format(obj, cls.__name__)
        error = None
        for cls_cat, cat_cls in cls._category_classes.items():
            bad_cats = cat_cls._not_categories
            cat_match = next((pc for pc in page_cats if cls_cat in pc and not any(bci in pc for bci in bad_cats)), None)
            if cat_match:
                if issubclass(cat_cls, cls):                # True for this class and its subclasses
                    return cat_cls, obj
                error = EntityTypeError(err_fmt.format(cls_cat, cat_match))

        if error:       # A match was found, but for a class that is not a subclass of this one
            raise error
        elif cls is not WikiEntity:
            # No match was found; only WikiEntity is allowed to be instantiated directly with no matching categories
            fmt = '{} has no categories that make it a {} or subclass thereof - page categories: {}'
            raise EntityTypeError(fmt.format(obj, cls.__name__, page_cats))
        return cls, obj

    @classmethod
    def _resolve_ambiguous(
            cls: Type[WE], page: WikiPage, existing: Optional[WE] = None, name: Optional[Name] = None, prompt=True
    ) -> Tuple[Type[WE], WikiPage]:
        """
        :param WikiPage page: A disambiguation page
        :param WikiEntity existing: An existing WikiEntity that the resolved page will be added to; used to filter
          disambiguation page links
        :param Name name: A Name to match, if no existing WikiEntity exists or if its parsed name is insufficient to
          filter results
        :param bool prompt: Attempt to interactively resolve disambiguation pages if unable to do so automatically
        :return tuple: Tuple of (WikiEntity subclass, WikiPage)
        """
        links = disambiguation_links(page)
        if not links:
            raise AmbiguousPageError(page_name(page), page, links)

        client, title_link_map = next(iter(site_titles_map(links).items()))     # type: MediaWikiClient, Dict[str, Link]
        pages = client.get_pages(title_link_map)
        candidates = {}
        for title, _page in pages.items():
            link = title_link_map[title]
            if _page.title != link.title:  # In case of redirects
                link = Link(f'[[{_page.title}]]', link.root)
            try:
                candidates[link] = cls._validate(_page)
            except EntityTypeError:
                pass

        # TODO: If a given site returned results, but none matched, and other sites returned matching results due to a
        #  redirect, then re-attempt the search on the sites that returned no relevant results, using the discovered id
        #  => Example: SNSD
        return handle_disambiguation_candidates(page, client, candidates, existing, name, prompt)

    @classmethod
    def _by_category(cls: Type[WE], obj: PageEntry, name: Optional[Name] = None, *args, **kwargs) -> WE:
        cat_cls, obj = cls._validate(obj, name=name)
        entity_name = obj.title if isinstance(obj, DiscoEntry) else page_name(obj)
        return cat_cls(entity_name, obj, *args, **kwargs)

    @classmethod
    def from_page(cls: Type[WE], page: WikiPage, *args, **kwargs) -> WE:
        return cls._by_category(page, *args, **kwargs)

    @classmethod
    def _from_multi_site_pages(cls: Type[WE], pages: Collection[WikiPage], name: Optional[Name] = None, strict=2) -> WE:
        # log.debug(f'Processing {len(pages)} multi-site pages')
        entity = None
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
                    entity = cat_cls(page_name(page), page)
                else:
                    entity._add_page(page)

        if entity is None:
            name = _name
            if page_link_map:
                raise AmbiguousPagesError(name, page_link_map)
            elif type_errors:
                raise EntityTypeError(f'Encountered {type_errors} type errors and found no valid pages for {name=!r}')
            else:
                raise ValueError(f'No pages found for {name=!r}')
        else:
            if page_link_map:
                lvl = logging.WARNING if strict else logging.DEBUG
                for page, links in page_link_map:
                    log.log(lvl, AmbiguousPageError(page_name(page), page, links))
            return entity

    @classmethod
    def from_title(cls: Type[WE], title: str, sites: StrOrStrs = None, search=True) -> WE:
        """
        :param str title: A page title
        :param iterable sites: A list or other iterable that yields site host strings
        :param bool search: Whether the provided title should also be searched for, in case there is not an exact match.
        :return: A WikiEntity (or subclass thereof) that represents the page(s) with the given title.
        """
        pages, errors = MediaWikiClient.get_multi_site_page(title, _sites(sites), search=search)
        if pages:
            return cls._from_multi_site_pages(pages.values())
        raise NoPagesFoundError(f'No pages found for title={title!r} from any of these sites: {", ".join(sites)}')

    @classmethod
    def from_titles(
            cls: Type[WE], titles: Iterable[Union[str, Name]], sites: StrOrStrs = None, search=True, strict=2
    ) -> Dict[Union[str, Name], WE]:
        """
        :param Iterable titles: Page titles to retrieve
        :param str|Iterable sites: Sites from which to retrieve them
        :param bool search: Resolve titles that may not be exact matches
        :param int strict: Error handling strictness.  If 2 (default), let all exceptions be propagated.  If 1, log
          EntityTypeError and AmbiguousPageError as a warning.  If 0, log those errors on debug level.
        :return dict: Mapping of {title: WikiEntity} for the given titles
        """
        titles, title_name_map = titles_and_title_name_map(titles)
        # log.debug(f'{title_name_map=}')
        query_map = {site: titles for site in _sites(sites)}
        # log.debug(f'Retrieving {cls.__name__}s: {query_map}', extra={'color': 14})
        log.debug(f'Retrieving {cls.__name__}s from sites={sorted(query_map)} with {titles=}')
        return cls._from_site_title_map(query_map, search, strict, title_name_map)

    @classmethod
    def _from_site_title_map(
            cls: Type[WE], site_title_map: Mapping[Union[str, MediaWikiClient], Iterable[str]], search=False, strict=2,
            title_name_map=None
    ) -> Dict[Union[str, Name], WE]:
        title_name_map = title_name_map or {}
        results, _errors = MediaWikiClient.get_multi_site_pages(site_title_map, search=search)
        for title, error in _errors.items():
            log.error(f'Error processing {title=!r}: {error}', extra={'color': 9})

        title_entity_map = {}
        for title, pages in multi_site_page_map(results).items():
            name = title_name_map.get(title)
            try:
                title_entity_map[name or title] = cls._from_multi_site_pages(pages, name, strict)
            except (EntityTypeError, AmbiguousPageError) as e:
                if strict > 1:
                    raise
                else:
                    log.log(logging.WARNING if strict else logging.DEBUG, e, extra={'color': 9})

        return title_entity_map

    @classmethod
    def from_url(cls: Type[WE], url: str) -> WE:
        return cls._by_category(MediaWikiClient.page_for_article(url))

    @classmethod
    def from_link(cls: Type[WE], link: Link) -> WE:
        mw_client, title = link_client_and_title(link)
        return cls._by_category(mw_client.get_page(title))

    @classmethod
    def find_from_links(cls: Type[WE], links: Iterable[Link]) -> WE:
        """
        :param links: An iterable that yields Link nodes.
        :return: The first instance of this class for a link that has a valid category for this class or a subclass
          thereof
        """
        last_exc = None
        results, errors = MediaWikiClient.get_multi_site_pages(site_titles_map(links))
        for site, pages in results.items():
            for title, page in pages.items():
                try:
                    return cls._by_category(page)
                except EntityTypeError as e:
                    last_exc = e

        if last_exc:
            raise last_exc
        raise ValueError(f'No pages were found')

    @classmethod
    def from_links(cls: Type[WE], links: Iterable[Link], strict=2) -> Dict[Link, WE]:
        link_entity_map = {}
        site_title_link_map = site_titles_map(links)
        title_entity_map = cls._from_site_title_map(site_title_link_map, False, strict)
        for title, entity in title_entity_map.items():
            for site, page in entity._pages.items():
                link = site_title_link_map[MediaWikiClient(site)][title]
                link_entity_map[link] = entity
        return link_entity_map


class EntertainmentEntity(WikiEntity):
    """An entity that may be related to the entertainment industry in some way.  Used to filter out irrelevant pages."""
    _categories = ()


class PersonOrGroup(EntertainmentEntity):
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
    _categories = ('agency', 'agencies', 'record label')


class SpecialEvent(EntertainmentEntity):
    _categories = ('competition',)


class TVSeries(EntertainmentEntity):
    _categories = ('television program', 'television series', 'drama')


class TemplateEntity(WikiEntity):
    _categories = ()

    @classmethod
    def from_name(cls, name: str, site: str) -> 'TemplateEntity':
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


def _sites(sites: StrOrStrs) -> List[str]:
    if isinstance(sites, str):
        sites = [sites]
    return sites or DEFAULT_WIKIS


# Down here due to circular dependency
from .parsing import WikiParser
