"""
Tkinter GUI menus

:author: Doug Skrypa
"""

from __future__ import annotations

import logging
from abc import ABCMeta, ABC, abstractmethod
from contextvars import ContextVar
from enum import Enum
from functools import partial
from tkinter import Event, Misc, TclError, Menu as TkMenu
from typing import TYPE_CHECKING, Optional, Union, Type, Callable, Any, Mapping, Iterator, Sequence

from .element import ElementBase
from .exceptions import NoActiveGroup

if TYPE_CHECKING:
    from ..pseudo_elements import Row
    from ..typing import Bool, XY

__all__ = ['MenuGroup', 'MenuItem', 'Menu', 'CopySelection']
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


# endregion


# region Menu Element, Items, and Groups


class MenuEntry(ABC):
    __slots__ = ('label', '_underline', 'enabled', 'show', 'keyword', '_format_label')

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

    def __set_name__(self, owner: Type[Menu], name: str):
        if not self.label:
            self.label = name

    def __repr__(self) -> str:
        underline, enabled, show = self._underline, self.enabled, self.show
        return f'<{self.__class__.__name__}({self.label!r}, {underline=}, {enabled=}, {show=})>'

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
    def maybe_add(self, menu: TkMenu, style: dict[str, Any], kwargs: dict[str, Any] = None) -> bool:
        raise NotImplementedError


class MenuItem(MenuEntry):
    __slots__ = ('callback', 'use_kwargs')

    def __init__(
        self,
        label: str,
        callback: Callable,
        *,
        underline: Union[str, int] = None,
        enabled: Mode = MenuMode.ALWAYS,
        show: Mode = None,
        keyword: str = None,
        use_kwargs: Bool = False,
        format_label: Bool = False,
    ):
        if show is None:
            show = MenuMode.KEYWORD if keyword else MenuMode.ALWAYS
        super().__init__(label, underline, enabled, show, keyword, format_label)
        self.callback = callback
        self.use_kwargs = use_kwargs

    def maybe_add(self, menu: TkMenu, style: dict[str, Any], kwargs: dict[str, Any] = None) -> bool:
        if not self.show.show(kwargs, self.keyword):
            return False

        callback = self.callback
        if self.use_kwargs and kwargs is not None:
            callback = partial(callback, **kwargs)

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

    def maybe_add(self, menu: TkMenu, style: dict[str, Any], kwargs: dict[str, Any] = None) -> bool:
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

    def __enter__(self) -> Menu:
        super().__enter__()
        if self.members is self.__class__.members:
            self.members = list(self.members)
        return self

    def style_kwargs(self) -> dict[str, Any]:
        style = self.style
        return {
            **style.get_map('menu', font='font', fg='fg', bg='bg'),
            **style.get_map('menu', 'disabled', disabledforeground='fg'),
        }

    def prepare(self, parent: Misc = None, kwargs: dict[str, Any] = None) -> TkMenu:
        style = self.style_kwargs()
        menu = TkMenu(parent, tearoff=0, **style)
        for member in self.members:
            member.maybe_add(menu, style, kwargs)

        return menu

    def pack_into(self, row: Row, column: int):
        # self.widget = menu = self.prepare(row.frame)
        # self.pack_widget()
        root = row.window._root
        self.widget = menu = self.prepare(root)
        root.configure(menu=menu)
        # self.pack_widget()

    def show(self, event: Event, parent: Misc = None, **kwargs):
        kwargs.setdefault('event', event)
        return self.popup((event.x_root, event.y_root), parent, **kwargs)

    def popup(self, position: XY = None, parent: Misc = None, **kwargs):
        menu = self.prepare(parent, kwargs)
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


class CopySelection(MenuItem):
    def __init__(
        self,
        label: str = 'Copy',
        *,
        underline: Union[str, int] = 0,
        enabled: Mode = MenuMode.TRUTHY,
        show: Mode = MenuMode.ALWAYS,
        keyword: str = 'selection',
        **kwargs,
    ):
        kwargs['use_kwargs'] = True
        super().__init__(
            label, self._copy_cb, underline=underline, enabled=enabled, show=show, keyword=keyword, **kwargs
        )

    def _copy_cb(self, event: Event, **kwargs):
        if selection := kwargs.get(self.keyword):
            event.widget.clipboard_clear()
            event.widget.clipboard_append(selection)

    def _add_selection(self, event: Event, kwargs: dict[str, Any]):
        widget: Misc = event.widget
        try:
            if widget != widget.selection_own_get():
                return
            kwargs[self.keyword] = widget.selection_get()
        except TclError as e:  # When no selection exists
            # log.debug(f'Error getting selection: {e}')
            pass

    def maybe_add(self, menu: TkMenu, style: dict[str, Any], kwargs: dict[str, Any]) -> bool:  # noqa
        event: Event = kwargs['event']
        if self.keyword not in kwargs:
            self._add_selection(event, kwargs)

        return super().maybe_add(menu, style, kwargs)


# endregion
