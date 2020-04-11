"""
A WikiEntity represents an entity that is represented by a page in one or more MediaWiki sites.

:author: Doug Skrypa
"""

import logging
from collections import defaultdict
from typing import Iterable, Optional, Union, Dict, Iterator, TypeVar, Type, Tuple, List

from ds_tools.input import choose_item
from wiki_nodes.http import MediaWikiClient
from wiki_nodes.page import WikiPage
from wiki_nodes.nodes import Link
from .disco_entry import DiscoEntry
from .exceptions import EntityTypeError, NoPagesFoundError, AmbiguousPageError
from .utils import site_titles_map, link_client_and_title, disambiguation_links, page_name

__all__ = ['WikiEntity', 'PersonOrGroup', 'Agency', 'SpecialEvent', 'TVSeries']
log = logging.getLogger(__name__)
DEFAULT_WIKIS = ['kpop.fandom.com', 'www.generasia.com', 'wiki.d-addicts.com', 'en.wikipedia.org']
WikiPage._ignore_category_prefixes = ('album chart usages for', 'discography article stubs')
WE = TypeVar('WE', bound='WikiEntity')
Pages = Union[Dict[str, WikiPage], Iterable[WikiPage], None]
PageEntry = Union[WikiPage, DiscoEntry]
StrOrStrs = Union[str, Iterable[str], None]


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
        self._name = name
        self.alt_names = None
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
        return f'<{self.__class__.__name__}({self._name!r})[pages: {len(self._pages)}]>'

    def _add_page(self, page: WikiPage):
        self._pages[page.site] = page

    def _add_pages(self, pages: Iterable[WikiPage]):
        for page in pages:
            self._pages[page.site] = page

    @property
    def pages(self) -> Iterator[WikiPage]:
        yield from self._pages.values()

    def page_parsers(self) -> Iterator[Tuple[WikiPage, 'WikiParser']]:
        for site, page in self._pages.items():
            try:
                parser = WikiParser.for_site(site)
            except KeyError:
                log.debug(f'No parser is configured for {page}')
            else:
                yield page, parser

    @classmethod
    def _validate(cls: Type[WE], obj: PageEntry) -> Tuple[Type[WE], PageEntry]:
        """
        :param WikiPage|DiscoEntry obj: A WikiPage or DiscoEntry to be validated against this class's categories
        :return tuple: Tuple of (WikiEntity subclass, page/entry)
        """
        page_cats = obj.categories
        if isinstance(obj, WikiPage) and any('disambiguation' in cat for cat in page_cats):
            return cls._resolve_ambiguous(obj)
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
    def _resolve_ambiguous(cls: Type[WE], page: WikiPage) -> Tuple[Type[WE], PageEntry]:
        links = disambiguation_links(page)
        if not links:
            raise AmbiguousPageError(page_name(page), page)

        client, title_link_map = next(iter(site_titles_map(links).items()))     # type: MediaWikiClient, Dict[str, Link]
        pages = client.get_pages(title_link_map)
        candidates = {}
        for title, page in pages.items():
            link = title_link_map[title]
            try:
                candidates[link] = cls._validate(page)
            except EntityTypeError:
                pass

        if not candidates:
            raise AmbiguousPageError(page_name(page), page, links)
        elif len(candidates) == 1:
            return next(iter(candidates.values()))
        else:
            # TODO: If there were results from other sites, compare names
            name = page_name(page)
            links = list(candidates)
            log.debug(f'Ambiguous title={name!r} on site={client.host} has too many candidates: {len(candidates)}')
            source = f'for ambiguous title={name!r} on {client.host}'
            link = choose_item(links, 'link', source, before=f'\nFound multiple candidate links {source}:')
            return candidates[link]

    @classmethod
    def _by_category(cls: Type[WE], obj: PageEntry, *args, **kwargs) -> WE:
        cat_cls, obj = cls._validate(obj)
        name = obj.title if isinstance(obj, DiscoEntry) else page_name(obj)
        return cat_cls(name, obj, *args, **kwargs)

    @classmethod
    def from_page(cls: Type[WE], page: WikiPage, *args, **kwargs) -> WE:
        return cls._by_category(page, *args, **kwargs)

    @classmethod
    def _from_multi_site_pages(cls: Type[WE], pages: Iterable[WikiPage]) -> WE:
        ipages = iter(pages)
        entity = cls.from_page(next(ipages))
        for page in ipages:
            cat_cls, page = cls._validate(page)
            entity._add_page(page)
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
    def from_titles(cls: Type[WE], titles: Iterable[str], sites: StrOrStrs = None, search=True) -> Dict[str, WE]:
        query_map = {site: titles for site in _sites(sites)}
        log.debug(f'Submitting queries: {query_map}')
        results, _errors = MediaWikiClient.get_multi_site_pages(query_map, search=search)
        for title, error in _errors.items():
            log.error(f'Error processing {title=!r}: {error}', extra={'color': 9})

        title_page_map = defaultdict(list)
        for site, pages in results.items():
            for title, page in pages.items():
                title_page_map[title].append(page)

        return {title: cls._from_multi_site_pages(pages) for title, pages in title_page_map.items()}

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
    def from_links(cls: Type[WE], links: Iterable[Link]) -> Dict[Link, WE]:
        link_entity_map = {}
        site_title_link_map = site_titles_map(links)
        results, errors = MediaWikiClient.get_multi_site_pages(site_title_link_map)
        for site, pages in results.items():
            title_link_map = site_title_link_map[MediaWikiClient(site)]
            for title, page in pages.items():
                link = title_link_map[title]
                try:
                    link_entity_map[link] = cls._by_category(page)
                except EntityTypeError as e:
                    log.debug(f'Error processing {link=}: {e}')

        return link_entity_map


class PersonOrGroup(WikiEntity):
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


class SpecialEvent(WikiEntity):
    _categories = ('competition',)


class TVSeries(WikiEntity):
    _categories = ('television program', 'television series', 'drama')


def _sites(sites: StrOrStrs) -> List[str]:
    if isinstance(sites, str):
        sites = [sites]
    return sites or DEFAULT_WIKIS


# Down here due to circular dependency
from .parsing import WikiParser
