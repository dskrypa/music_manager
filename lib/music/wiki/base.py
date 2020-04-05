"""
A WikiEntity represents an entity that is represented by a page in one or more MediaWiki sites.

:author: Doug Skrypa
"""

import logging
from typing import Iterable, Optional, Union, Dict, Iterator, TypeVar, Any, Type, Tuple

from wiki_nodes.http import MediaWikiClient
from wiki_nodes.page import WikiPage
from wiki_nodes.nodes import Link
from .exceptions import EntityTypeError, NoPagesFoundError, NoLinkTarget, NoLinkSite
from .utils import site_titles_map

__all__ = ['WikiEntity', 'PersonOrGroup', 'Agency', 'SpecialEvent', 'TVSeries']
log = logging.getLogger(__name__)
DEFAULT_WIKIS = ['kpop.fandom.com', 'www.generasia.com', 'wiki.d-addicts.com', 'en.wikipedia.org']
WikiPage._ignore_category_prefixes = ('album chart usages for', 'discography article stubs')
WE = TypeVar('WE', bound='WikiEntity')
Pages = Union[Dict[str, WikiPage], Iterable[WikiPage], None]


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
        :param WikiPage|dict|iterable pages: One or more WikiPage objects
        """
        self._name = name
        self.alt_names = None
        if isinstance(pages, Dict):
            self._pages = pages         # type: Dict[str, WikiPage]
        else:
            self._pages = {}            # type: Dict[str, WikiPage]
            if pages:
                if isinstance(pages, str):
                    raise TypeError(f'pages must be a WikiPage, or dict of site:WikiPage, or list of WikiPage objs')
                elif isinstance(pages, WikiPage):
                    self._pages[pages.site] = pages
                else:
                    for page in pages:
                        self._pages[page.site] = page

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
    def _by_category(
            cls: Type[WE], name: str, obj: Union[WikiPage, Any], page_cats: Iterable[str], *args, **kwargs
    ) -> WE:
        err_fmt = '{} is incompatible with {} due to category={{!r}} [{{!r}}]'.format(obj, cls.__name__)
        error = None
        for cls_cat, cat_cls in cls._category_classes.items():
            bad_cats = cat_cls._not_categories
            cat_match = next((pc for pc in page_cats if cls_cat in pc and not any(bci in pc for bci in bad_cats)), None)
            if cat_match:
                if issubclass(cat_cls, cls):                # True for this class and its subclasses
                    return cat_cls(name, *args, **kwargs)
                error = EntityTypeError(err_fmt.format(cls_cat, cat_match))

        if error:       # A match was found, but for a class that is not a subclass of this one
            raise error
        elif cls is not WikiEntity:
            # No match was found; only WikiEntity is allowed to be instantiated directly with no matching categories
            fmt = '{} has no categories that make it a {} or subclass thereof - page categories: {}'
            raise EntityTypeError(fmt.format(obj, cls.__name__, page_cats))
        return cls(name, *args, **kwargs)

    @classmethod
    def from_page(cls: Type[WE], page: WikiPage, *args, **kwargs) -> WE:
        name = page.title
        if page.infobox:
            try:
                name = page.infobox['name'].value
            except KeyError:
                pass

        return cls._by_category(name, page, page.categories, [page], *args, **kwargs)

    @classmethod
    def from_title(cls: Type[WE], title: str, sites: Optional[Iterable[str]] = None, search=True) -> WE:
        """
        :param str title: A page title
        :param iterable sites: A list or other iterable that yields site host strings
        :param bool search: Whether the provided title should also be searched for, in case there is not an exact match.
        :return: A WikiEntity (or subclass thereof) that represents the page(s) with the given title.
        """
        if isinstance(sites, str):
            sites = [sites]
        sites = sites or DEFAULT_WIKIS
        pages, errors = MediaWikiClient.get_multi_site_page(title, sites, search=search)
        if pages:
            ipages = iter(pages.values())
            obj = cls.from_page(next(ipages))
            obj._add_pages(ipages)
            return obj
        raise NoPagesFoundError(f'No pages found for title={title!r} from any of these sites: {", ".join(sites)}')

    @classmethod
    def from_url(cls: Type[WE], url: str) -> WE:
        return cls.from_page(MediaWikiClient.page_for_article(url))

    @classmethod
    def from_link(cls: Type[WE], link: Link) -> WE:
        if not link.source_site:
            raise NoLinkSite(link)
        mw_client = MediaWikiClient(link.source_site)
        title = link.title
        if link.interwiki:
            iw_key, title = link.iw_key_title
            mw_client = mw_client.interwiki_client(iw_key)
        elif not title:
            raise NoLinkTarget(link)
        return cls.from_page(mw_client.get_page(title))

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
                    return cls.from_page(page)
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
                    link_entity_map[link] = cls.from_page(page)
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


# Down here due to circular dependency
from .parsing import WikiParser
