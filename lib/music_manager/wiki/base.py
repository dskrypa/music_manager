"""
:author: Doug Skrypa
"""

import logging

from ds_tools.wiki.http import MediaWikiClient
from ds_tools.wiki.page import WikiPage
from .exceptions import EntityTypeError

__all__ = ['WikiEntity', 'PersonOrGroup', 'Agency', 'SpecialEvent', 'TVSeries']
log = logging.getLogger(__name__)


class WikiEntity:
    _categories = ()
    _category_classes = {}

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        for cat in cls._categories:
            WikiEntity._category_classes[cat] = cls

    def __init__(self, name, pages=None):
        """
        :param str name: The name of this entity
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

        for category, cat_cls in cls._category_classes.items():
            if any(category in cat for cat in page.categories):
                if issubclass(cat_cls, cls):
                    return cat_cls(name, [page], *args, **kwargs)
                raise EntityTypeError(f'{page} is incompatible with {cls.__name__} due to category={category!r}')

        return cls(name, [page], *args, **kwargs)

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
