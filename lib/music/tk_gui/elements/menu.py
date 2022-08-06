"""
Tkinter GUI menus

:author: Doug Skrypa
"""

from __future__ import annotations

import logging
from abc import ABCMeta, ABC, abstractmethod
from contextvars import ContextVar
from enum import Enum
from itertools import count
from tkinter import Event, Misc, TclError, Menu as TkMenu
from typing import TYPE_CHECKING, Optional, Union, Type, Any, Mapping, Iterator, Sequence
from urllib.parse import quote_plus, urlparse

from ..utils import get_top_level
from .element import ElementBase
from .exceptions import NoActiveGroup

if TYPE_CHECKING:
    from ..pseudo_elements import Row
    from ..typing import Bool, XY, EventCallback

__all__ = [
    'MenuGroup', 'MenuItem', 'Menu',
    'SelectionMenuItem', 'CopySelection',
    'SearchSelection', 'GoogleSelection', 'GoogleTranslate', 'SearchWikipedia',
    'SearchKpopFandom', 'SearchGenerasia', 'SearchDramaWiki',
]
log = logging.getLogger(__name__)

_menu_group_stack = ContextVar('tk_gui.elements.menu.stack', default=[])
Mode = Union['MenuMode', str, bool, None]


class MenuMode(Enum):
    ALWAYS = 'always'
    NEVER = 'never'         #
    KEYWORD = 'keyword'     # Enable when the specified keyword is present
    TRUTHY = 'truthy'       # Enable when the specified keyword's value is truthy

    @classmethod
    def _missing_(cls, value: Union[str, bool]):
        if value is True:
            return cls.ALWAYS
        elif value is False:
            return cls.NEVER
        try:
            return cls[value.upper().replace(' ', '_')]
        except KeyError:
            return None  # This is what the default implementation does to signal an exception should be raised

    def enabled(self, kwargs: Mapping[str, Any] = None, keyword: str = None) -> bool:
        try:
            return _MODE_TRUTH_MAP[self]
        except KeyError:
            pass
        if not kwargs or not keyword:
            return False
        try:
            value = kwargs[keyword]
        except KeyError:
            return False
        if self == self.KEYWORD:
            return True
        else:
            return bool(value)

    show = enabled


# region Internal Helpers


_MODE_TRUTH_MAP = {MenuMode.ALWAYS: True, MenuMode.NEVER: False}


class ContainerMixin:
    members: list[Union[MenuEntry, MenuItem, MenuGroup]]

    def __enter__(self) -> ContainerMixin:
        _menu_group_stack.get().append(self)
        return self

    def __exit__(self, exc_type=None, exc_val=None, exc_tb=None):
        _menu_group_stack.get().pop()

    def __getitem__(self, index: int) -> Union[MenuEntry, MenuItem, MenuGroup]:
        return self.members[index]

    def __iter__(self) -> Iterator[Union[MenuEntry, MenuItem, MenuGroup]]:
        yield from self.members


class EntryContainer(ContainerMixin):
    __slots__ = ('members',)

    def __init__(self):
        self.members: list[Union[MenuEntry, MenuItem, MenuGroup]] = []


def get_current_menu_group(silent: bool = False) -> Optional[ContainerMixin]:
    """
    Get the currently active MenuGroup.

    :param silent: If True, allow this function to return ``None`` if there is no active :class:`MenuGroup`
    :return: The active :class:`MenuGroup` object
    :raises: :class:`~.exceptions.NoActiveGroup` if there is no active MenuGroup and ``silent=False`` (default)
    """
    try:
        return _menu_group_stack.get()[-1]
    except (AttributeError, IndexError):
        if silent:
            return None
        raise NoActiveGroup('There is no active context') from None


class MenuMeta(ABCMeta, type):
    _containers: dict[tuple[str, tuple[type, ...]], EntryContainer] = {}

    @classmethod
    def __prepare__(mcs, name: str, bases: tuple[type, ...]) -> dict:
        """
        Called before ``__new__`` and before evaluating the contents of a class, which facilitates the creation of an
        :class:`EntryContainer` that unnamed :class:`MenuEntry` instances can register themselves with.  That
        container's members are transferred to the new :class:`Menu` subclass when the subclass is created in
        :meth:`.__new__`.
        """
        mcs._containers[(name, bases)] = container = EntryContainer()
        container.__enter__()
        return {}

    def __new__(mcs, name: str, bases: tuple[type, ...], namespace: dict[str, Any]):
        container = mcs._containers.pop((name, bases))
        container.__exit__()
        cls = super().__new__(mcs, name, bases, namespace)
        cls.members = container.members
        del container
        return cls


class CallbackMetadata:
    __slots__ = ('menu_item', 'result', 'event', 'args', 'kwargs')

    def __init__(
        self,
        menu_item: MenuItem,
        result: Any,
        event: Event = None,
        args: Sequence[Any] = (),
        kwargs: dict[str, Any] = None,
    ):
        self.menu_item = menu_item
        self.result = result
        self.event = event
        self.args = args
        self.kwargs = kwargs

    def __repr__(self) -> str:
        content = ',\n    '.join(f'{k}={getattr(self, k)!r}' for k in self.__slots__)
        return f'<{self.__class__.__name__}(\n    {content}\n)>'


def wrap_menu_cb(
    menu_item: MenuItem,
    func: EventCallback,
    event: Event = None,
    store_meta: Bool = False,
    args: Sequence[Any] = (),
    kwargs: dict[str, Any] = None,
):
    kwargs = kwargs or {}

    def run_menu_cb():
        result = func(event, *args, **kwargs)
        if store_meta:
            result = CallbackMetadata(menu_item, result, event, args, kwargs)

        widget = event.widget if event else menu_item.root_menu.widget
        num = menu_item.root_menu.add_result(result)
        get_top_level(widget).event_generate('<<Custom:MenuCallback>>', state=num)

    return run_menu_cb


# endregion


# region Menu Element, Items, and Groups


class MenuEntry(ABC):
    __slots__ = ('parent', 'label', '_underline', 'enabled', 'show', 'keyword', '_format_label')

    def __init__(
        self,
        label: str = None,
        underline: Union[str, int] = None,
        enabled: Mode = MenuMode.ALWAYS,
        show: Mode = MenuMode.ALWAYS,
        keyword: str = None,
        format_label: Bool = False,
    ):
        self.label = label
        self._underline = underline
        self.enabled = MenuMode(enabled)
        self.show = MenuMode(show)
        self.keyword = keyword
        self._format_label = format_label
        if group := get_current_menu_group(True):
            group.members.append(self)
            self.parent = group
        else:
            self.parent = None

    def __set_name__(self, owner: Type[Menu], name: str):
        if not self.label:
            self.label = name

    def __repr__(self) -> str:
        underline, enabled, show = self._underline, self.enabled, self.show
        return f'<{self.__class__.__name__}({self.label!r}, {underline=}, {enabled=}, {show=})>'

    @property
    def root_menu(self) -> Optional[Menu]:
        parent = self.parent
        if parent is None or isinstance(parent, Menu):
            return parent
        return parent.parent

    @property
    def underline(self) -> Optional[int]:
        underline = self._underline
        try:
            return int(underline)
        except (TypeError, ValueError):
            pass
        try:
            return self.label.index(underline)
        except (ValueError, TypeError):
            return None

    def format_label(self, kwargs: dict[str, Any] = None) -> str:
        if self._format_label and kwargs is not None:
            return self.label.format(**kwargs)
        return self.label

    @abstractmethod
    def maybe_add(
        self, menu: TkMenu, style: dict[str, Any], event: Event = None, kwargs: dict[str, Any] = None
    ) -> bool:
        raise NotImplementedError


class MenuItem(MenuEntry):
    __slots__ = ('callback', 'use_kwargs', 'store_meta')

    def __init__(
        self,
        label: str,
        callback: EventCallback,
        *,
        underline: Union[str, int] = None,
        enabled: Mode = MenuMode.ALWAYS,
        show: Mode = None,
        keyword: str = None,
        use_kwargs: Bool = False,
        format_label: Bool = False,
        store_meta: Bool = False,
    ):
        if show is None:
            show = MenuMode.KEYWORD if keyword else MenuMode.ALWAYS
        super().__init__(label, underline, enabled, show, keyword, format_label)
        self.callback = callback
        self.use_kwargs = use_kwargs
        self.store_meta = store_meta

    def maybe_add(
        self, menu: TkMenu, style: dict[str, Any], event: Event = None, kwargs: dict[str, Any] = None
    ) -> bool:
        if not self.show.show(kwargs, self.keyword):
            return False

        callback = self.callback
        if self.use_kwargs and kwargs is not None:
            callback = wrap_menu_cb(self, callback, event, self.store_meta, kwargs=kwargs)
        else:
            callback = wrap_menu_cb(self, callback, event, self.store_meta)

        label = self.format_label(kwargs)
        menu.add_command(label=label, underline=self.underline, command=callback)
        if not self.enabled.enabled(kwargs, self.keyword):
            menu.entryconfigure(label, state='disabled')

        return True


class MenuGroup(ContainerMixin, MenuEntry):
    __slots__ = ('members',)

    def __init__(self, label: Optional[str], underline: Union[str, int] = None, *args, **kwargs):
        super().__init__(label, underline, *args, **kwargs)
        self.members: list[Union[MenuEntry, MenuItem, MenuGroup]] = []

    def __repr__(self) -> str:
        label, underline, enabled, show = self.label, self.underline, self.enabled, self.show
        return f'<{self.__class__.__name__}({label!r}, {underline=}, {enabled=}, {show=})[members={len(self.members)}]>'

    def maybe_add(
        self, menu: TkMenu, style: dict[str, Any], event: Event = None, kwargs: dict[str, Any] = None
    ) -> bool:
        if not self.show.show(kwargs, self.keyword):
            return False

        sub_menu = TkMenu(menu, tearoff=0, **style)
        added_any = False
        for member in self.members:
            added_any |= member.maybe_add(sub_menu, style, kwargs)

        cascade_kwargs = {'label': self.format_label(kwargs)}
        if not added_any or not self.enabled.enabled(kwargs, self.keyword):
            cascade_kwargs['state'] = 'disabled'

        menu.add_cascade(menu=sub_menu, underline=self.underline, **cascade_kwargs)
        return True


class Menu(ContainerMixin, ElementBase, metaclass=MenuMeta):
    """A menu bar or right-click menu"""

    _result_counter = count()
    results = {}
    widget: TkMenu
    members: Sequence[Union[MenuEntry, MenuItem, MenuGroup]]

    def __init__(self, members: Sequence[Union[MenuEntry, MenuItem, MenuGroup]] = None, **kwargs):
        super().__init__(**kwargs)
        if members is not None:
            if self.members:
                self.members = all_members = list(self.members)
                all_members.extend(members)
            else:
                self.members = members
        for member in self.members:
            member.parent = self

    def add_result(self, result: Any) -> int:
        num = next(self._result_counter)
        self.results[num] = result
        return num

    def __enter__(self) -> Menu:
        super().__enter__()
        if self.members is self.__class__.members:
            self.members = list(self.members)
        return self

    @property
    def style_config(self) -> dict[str, Any]:
        style = self.style
        return {
            **style.get_map('menu', font='font', fg='fg', bg='bg', bd='border_width', relief='relief'),
            **style.get_map('menu', 'disabled', disabledforeground='fg'),
            **style.get_map('menu', 'active', activeforeground='fg', activebackground='bg'),
            **self._style_config,
        }

    def prepare(self, parent: Misc = None, event: Event = None, kwargs: dict[str, Any] = None) -> TkMenu:
        style = self.style_config
        menu = TkMenu(parent, tearoff=0, takefocus=int(self.allow_focus), **style)
        for member in self.members:
            member.maybe_add(menu, style, event, kwargs)

        return menu

    def pack_into(self, row: Row, column: int):
        root = row.window._root
        self.widget = menu = self.prepare(root)
        root.configure(menu=menu)

    def show(self, event: Event, parent: Misc = None, **kwargs):
        return self.popup((event.x_root, event.y_root), parent, event, **kwargs)

    def popup(self, position: XY = None, parent: Misc = None, event: Event = None, **kwargs):
        menu = self.prepare(parent, event, kwargs)
        try:
            _x, _y = position
        except (TypeError, ValueError):
            position = self.window.mouse_position
        try:
            menu.tk_popup(*position)
        finally:
            menu.grab_release()


# endregion


# region Custom Menu Items


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
