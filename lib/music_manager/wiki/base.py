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

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        for cat in cls._categories:
            WikiEntity._category_classes[cat] = cls

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
    def _by_category(cls, name, obj, categories, *args, **kwargs):
        error = None
        for category, cat_cls in cls._category_classes.items():
            bad_cat = next((nc for cat in categories for nc in cat_cls._not_categories if nc in cat), None)
            if bad_cat:
                if cat_cls is cls:  # Ignore subclasses
                    error = EntityTypeError(f'{obj} is incompatible with {cls.__name__} due to category={bad_cat!r}')
            else:
                if any(category in cat for cat in categories):
                    if issubclass(cat_cls, cls):
                        return cat_cls(name, *args, **kwargs)
                    error = EntityTypeError(f'{obj} is incompatible with {cls.__name__} due to category={category!r}')

        if error:
            raise error
        return cls(name, *args, **kwargs)

    @classmethod
    def from_title(cls, title, sites=None):
        sites = sites or DEFAULT_WIKIS
        pages, errors = MediaWikiClient.get_multi_site_page(title, sites)
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


class Agency(PersonOrGroup):
    _categories = ('agency', 'agencies', 'record label')


class SpecialEvent(WikiEntity):
    _categories = ('competition',)


class TVSeries(WikiEntity):
    _categories = ('television program', 'television series', 'drama')
