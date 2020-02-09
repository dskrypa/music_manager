"""
:author: Doug Skrypa
"""

import logging

from ds_tools.wiki.http import MediaWikiClient
from ds_tools.wiki.page import WikiPage
from .exceptions import EntityTypeError, NoPagesFoundError

__all__ = ['WikiEntity', 'PersonOrGroup', 'Agency', 'SpecialEvent', 'TVSeries']
log = logging.getLogger(__name__)
DEFAULT_WIKIS = ['kpop.fandom.com', 'www.generasia.com', 'wiki.d-addicts.com', 'en.wikipedia.org']
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

    def __init__(self, name, pages=None):
        """
        :param str|None name: The name of this entity
        :param WikiPage|dict|iterable pages: One or more WikiPage objects
        """
        self.name = name
        self.alt_names = None
        if isinstance(pages, dict):
            self._pages = pages
        else:
            self._pages = {}
            if pages:
                if isinstance(pages, str):
                    raise TypeError(f'pages must be a WikiPage, or dict of site:WikiPage, or list of WikiPage objs')
                elif isinstance(pages, WikiPage):
                    self._pages[pages.site] = pages
                else:
                    for page in pages:
                        self._pages[page.site] = page

    def __repr__(self):
        return f'<{type(self).__name__}({self.name!r})[pages: {len(self._pages)}]>'

    def __to_json__(self):
        """Not possible to build from json, so just provide the repr for easy printing"""
        return repr(self)

    def _add_page(self, page):
        self._pages[page.site] = page

    def _add_pages(self, pages):
        for page in pages:
            self._pages[page.site] = page

    @property
    def pages(self):
        yield from self._pages.values()

    @classmethod
    def from_page(cls, page, *args, **kwargs):
        name = page.title
        if page.infobox:
            try:
                name = page.infobox['name'].value
            except KeyError:
                pass

        return cls._by_category(name, page, page.categories, [page], *args, **kwargs)

    @classmethod
    def _by_category(cls, name, obj, page_cats, *args, **kwargs):
        error = None
        for category, cat_cls in cls._category_classes.items():
            bad_cat = next((nc for cat in page_cats for nc in cat_cls._not_categories if nc in cat), None)
            if bad_cat:
                if cat_cls is cls:  # Ignore subclasses
                    error = EntityTypeError(f'{obj} is incompatible with {cls.__name__} due to category={bad_cat!r}')
            else:
                if any(category in cat for cat in page_cats):
                    if issubclass(cat_cls, cls):
                        return cat_cls(name, *args, **kwargs)
                    error = EntityTypeError(f'{obj} is incompatible with {cls.__name__} due to category={category!r}')

        if error:           # I can't help but feel like this may bite me eventually...
            raise error

        if cls is not WikiEntity and not cls._categories:
            # for sub_cls in cls._subclasses[cls]:
            raise EntityTypeError(f'{obj} has no categories that make it a {cls.__name__} or subclass thereof')

        return cls(name, *args, **kwargs)

    @classmethod
    def from_title(cls, title, sites=None, search=True):
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
    def from_url(cls, url):
        return cls.from_page(MediaWikiClient.page_for_article(url))


class PersonOrGroup(WikiEntity):
    _categories = ()

    @classmethod
    def from_name(cls, name, affiliations=None, sites=None):
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
