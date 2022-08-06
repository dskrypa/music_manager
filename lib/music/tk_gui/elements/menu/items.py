"""
Tkinter GUI custom menu items

:author: Doug Skrypa
"""

from __future__ import annotations

import logging
from abc import ABC
from tkinter import Event, Misc, TclError, Menu as TkMenu
from typing import TYPE_CHECKING, Union, Any
from urllib.parse import quote_plus, urlparse

from ...utils import get_selection_pos
from .menu import MenuItem, Mode
from .utils import MenuMode

if TYPE_CHECKING:
    from ...typing import Bool

__all__ = [
    'SelectionMenuItem', 'CopySelection', 'PasteClipboard',
    'SearchSelection', 'GoogleSelection', 'GoogleTranslate', 'SearchWikipedia',
    'SearchKpopFandom', 'SearchGenerasia', 'SearchDramaWiki',
]
log = logging.getLogger(__name__)


# region Selection Menu Items


class SelectionMenuItem(MenuItem):
    def __init__(self, *args, enabled: Mode = MenuMode.TRUTHY, keyword: str = 'selection', **kwargs):
        kwargs['use_kwargs'] = True
        super().__init__(*args, enabled=enabled, keyword=keyword, **kwargs)

    def maybe_add_selection(self, event: Event, kwargs: dict[str, Any]):
        if self.keyword in kwargs:
            return
        widget: Misc = event.widget
        try:
            if widget != widget.selection_own_get():
                return
            kwargs[self.keyword] = widget.selection_get()
        # except TclError as e:  # When no selection exists
        except TclError:
            # log.debug(f'Error getting selection: {e}')
            pass

    def maybe_add(self, menu: TkMenu, style: dict[str, Any], event: Event, kwargs: dict[str, Any]) -> bool:  # noqa
        self.maybe_add_selection(event, kwargs)
        return super().maybe_add(menu, style, event, kwargs)


class CopySelection(SelectionMenuItem):
    def __init__(self, label: str = 'Copy', *, underline: Union[str, int] = 0, show: Mode = MenuMode.ALWAYS, **kwargs):
        super().__init__(label, self._copy_cb, underline=underline, show=show, store_meta=True, **kwargs)

    def _copy_cb(self, event: Event, **kwargs):
        if selection := kwargs.get(self.keyword):
            widget: Misc = event.widget
            widget.clipboard_clear()
            widget.clipboard_append(selection)


class PasteClipboard(SelectionMenuItem):
    def __init__(self, label: str = 'Paste', *, underline: Union[str, int] = 0, show: Mode = MenuMode.ALWAYS, **kwargs):
        kwargs['enabled'] = MenuMode.ALWAYS
        super().__init__(label, self._paste_cb, underline=underline, show=show, store_meta=True, **kwargs)

    def _paste_cb(self, event: Event, **kwargs):
        widget: Misc = event.widget
        try:
            if widget['state'] != 'normal':
                return
        except TclError:
            return

        first, last = get_selection_pos(widget, raw=True)  # noqa
        try:
            text = widget.clipboard_get()
            if first is None:
                widget.insert('insert', text)  # noqa
            else:
                try:
                    widget.replace(first, last, text)  # noqa
                except AttributeError:
                    widget.delete(first, last)  # noqa
                    widget.insert(first, text)  # noqa
        except (AttributeError, TclError):
            pass


# endregion


# region Search Engines


class SearchSelection(SelectionMenuItem, ABC):
    title: str
    url_fmt: str

    def __init_subclass__(cls, url: str, title: str = None):  # noqa
        expected = '{query}'
        if expected not in url:
            raise ValueError(f'Invalid {url=} - expected a format string with {expected!r} in place of the query')
        if title is None:
            title = urlparse(url).hostname
            if title.startswith('www.') and len(title) > 4:
                title = title[4:]

        cls.title = title
        cls.url_fmt = url

    def __init__(self, label: str = None, *, keyword: str = 'selection', quote: Bool = True, **kwargs):
        if label is None:
            label = f'Search {self.title} for {{{keyword}!r}}'
        kwargs['format_label'] = True
        super().__init__(label, self._search_cb, keyword=keyword, **kwargs)
        self.quote = quote

    def _search_cb(self, event: Event, **kwargs):
        if not (selection := kwargs.get(self.keyword)):
            return

        import webbrowser

        if self.quote:
            selection = quote_plus(selection)

        url = self.url_fmt.format(query=selection)
        log.debug(f'Opening {url=}')
        webbrowser.open(url)


class GoogleSelection(SearchSelection, title='Google', url='https://www.google.com/search?q={query}'):
    pass


class GoogleTranslate(SearchSelection, url='https://translate.google.com/?sl=auto&tl=en&text={query}&op=translate'):
    def __init__(self, label: str = None, *, keyword: str = 'selection', **kwargs):
        super().__init__(label or f'Translate {{{keyword}!r}}', keyword=keyword, **kwargs)


class SearchWikipedia(
    SearchSelection,
    title='Wikipedia',
    url='https://en.wikipedia.org/w/index.php?search={query}&title=Special%3ASearch&fulltext=Search&ns0=1',
):
    pass


class SearchKpopFandom(SearchSelection, url='https://kpop.fandom.com/wiki/Special:Search?scope=internal&query={query}'):
    pass


class SearchGenerasia(
    SearchSelection, url='https://www.generasia.com/w/index.php?title=Special%3ASearch&fulltext=Search&search={query}'
):
    pass


class SearchDramaWiki(SearchSelection, title='DramaWiki', url='https://wiki.d-addicts.com/index.php?search={query}'):
    pass


# endregion
