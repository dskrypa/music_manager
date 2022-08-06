"""
Tkinter GUI menus

:author: Doug Skrypa
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from itertools import count
from tkinter import Event, Misc, Menu as TkMenu
from typing import TYPE_CHECKING, Optional, Union, Type, Any, Sequence

from ..element import ElementBase
from .utils import MenuMode, ContainerMixin, MenuMeta, get_current_menu_group, wrap_menu_cb

if TYPE_CHECKING:
    from ...pseudo_elements import Row
    from ...typing import Bool, XY, EventCallback

__all__ = ['Mode', 'MenuEntry', 'MenuItem', 'MenuGroup', 'Menu', 'CustomMenuItem']

Mode = Union['MenuMode', str, bool, None]


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
    __slots__ = ('_callback', 'use_kwargs', 'store_meta')

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
        self._callback = callback
        self.use_kwargs = use_kwargs
        self.store_meta = store_meta

    def maybe_add(
        self, menu: TkMenu, style: dict[str, Any], event: Event = None, kwargs: dict[str, Any] = None
    ) -> bool:
        if not self.show.show(kwargs, self.keyword):
            return False

        callback = self._callback
        if self.use_kwargs and kwargs is not None:
            callback = wrap_menu_cb(self, callback, event, self.store_meta, kwargs=kwargs)
        else:
            callback = wrap_menu_cb(self, callback, event, self.store_meta)

        label = self.format_label(kwargs)
        menu.add_command(label=label, underline=self.underline, command=callback)
        if not self.enabled.enabled(kwargs, self.keyword):
            menu.entryconfigure(label, state='disabled')

        return True


class CustomMenuItem(MenuItem, ABC):
    __slots__ = ()

    def __init__(self, label: str, **kwargs):
        super().__init__(label, self.callback, **kwargs)

    @abstractmethod
    def callback(self, event: Event, **kwargs) -> Any:
        raise NotImplementedError


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
            added_any |= member.maybe_add(sub_menu, style, event, kwargs)

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
