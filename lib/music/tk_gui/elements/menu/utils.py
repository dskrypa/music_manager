"""
Tkinter GUI menu utils

:author: Doug Skrypa
"""

from __future__ import annotations

from abc import ABCMeta
from contextvars import ContextVar
from enum import Enum
from tkinter import Event, Entry, Text, Misc, TclError, StringVar
from typing import TYPE_CHECKING, Optional, Union, Any, Mapping, Iterator, Sequence

from music.text.extraction import split_enclosed
from music.tk_gui.utils import get_top_level
from ..exceptions import NoActiveGroup

if TYPE_CHECKING:
    from ...typing import Bool, EventCallback
    from .menu import MenuItem, MenuGroup, MenuEntry

__all__ = ['MenuMode', 'CallbackMetadata']

_menu_group_stack = ContextVar('tk_gui.elements.menu.stack', default=[])


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


# region Menu Item Text Helpers


def get_text(widget: Union[Entry, Text]) -> str:
    try:
        return widget.get()
    except TypeError:
        return widget.get(0)


def get_any_text(widget: Misc) -> Optional[str]:
    try:
        return get_text(widget)  # noqa
    except (AttributeError, TypeError, TclError):
        pass
    try:
        return widget['text']
    except TclError:
        pass
    try:
        var: StringVar = widget['textvariable']
    except TclError:
        return None
    else:
        return var.get()


def replace_selection(widget: Union[Entry, Text], text: str, first: Union[str, int], last: Union[str, int]):
    try:
        widget.replace(first, last, text)
    except AttributeError:
        widget.delete(first, last)
        widget.insert(first, text)


def flip_name_parts(text: str) -> str:
    try:
        a, b = split_enclosed(text, maxsplit=1)
    except ValueError:
        return text
    else:
        return f'{b} ({a})'


# endregion
