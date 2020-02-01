"""
:author: Doug Skrypa
"""

import logging

from ds_tools.wiki.http import MediaWikiClient
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
        self.name = name
        self.alt_names = None
        self.pages = pages or []

    def __repr__(self):
        return f'<{type(self).__name__}({self.name!r})[pages: {len(self.pages)}]>'

    @classmethod
    def from_page(cls, page):
        name = page.title
        if page.infobox:
            try:
                name = page.infobox['name']
            except KeyError:
                pass

        for category, cat_cls in cls._category_classes.items():
            if any(category in cat for cat in page.categories):
                if issubclass(cat_cls, cls):
                    return cat_cls(name, [page])
                raise EntityTypeError(f'{page} is incompatible with {cls.__name__} due to category={category!r}')

        return cls(name, [page])

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
