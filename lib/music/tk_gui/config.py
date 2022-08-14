"""
Music Manager GUI config

:author: Doug Skrypa
"""

from __future__ import annotations

import json
import logging
from inspect import isclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Type, Union, Optional, Callable, TypeVar, Generic

from ..__version__ import __title__

if TYPE_CHECKING:
    from .window import Window

__all__ = ['WindowConfig', 'WindowConfigProperty']
log = logging.getLogger(__name__)

_NotSet = object()
DEFAULT_DIR = '~/.config'
DEFAULT_NAME = 'tk_gui_config.json'
DEFAULT_PATH = f'{DEFAULT_DIR}/{__title__}/{DEFAULT_NAME}'
DEFAULT_SECTION = '__default__'

T = TypeVar('T')


class ConfigItem(Generic[T]):
    __slots__ = ('name', 'default', 'type', 'popup_dependent', 'depends_on')

    def __init__(
        self,
        default,
        type: Callable[[Any], T] = None,  # noqa
        popup_dependent: bool = False,
        depends_on: ConfigItem = None,
    ):
        self.default = default
        self.type = type
        self.popup_dependent = popup_dependent
        self.depends_on = depends_on
        if popup_dependent and depends_on:
            raise ValueError('depends_on cannot be combined with popup_dependent')

    def __set_name__(self, owner: Type[WindowConfig], name: str):
        self.name = name

    def get(self, instance: WindowConfig) -> Optional[T]:
        try:
            value = instance._get(self.name, type=self.type)
        except KeyError:
            if self.popup_dependent:
                return self.default[instance.is_popup]
            return self.default

        if (depends_on := self.depends_on) and not depends_on.get(instance):
            return self.default
        return value

    def __get__(self, instance: Optional[WindowConfig], owner: Type[WindowConfig]) -> Union[T, None, ConfigItem]:
        if instance is None:
            return self
        return self.get(instance)

    def __set__(self, instance: WindowConfig, value: T):
        if value is not _NotSet and self.get(instance) != value:
            instance[self.name] = value

    def __delete__(self, instance: WindowConfig):
        del instance[self.name]


class WindowConfig:
    auto_save = ConfigItem((True, False), bool, popup_dependent=True)
    style = ConfigItem(None, str)
    remember_size = ConfigItem((True, False), bool, popup_dependent=True)
    remember_position = ConfigItem((True, False), bool, popup_dependent=True)
    size = ConfigItem(None, tuple, depends_on=remember_size)
    position = ConfigItem(None, tuple, depends_on=remember_position)

    def __init__(
        self,
        name: Optional[str],
        path: Union[str, Path] = None,
        defaults: dict[str, Any] = None,
        is_popup: bool = False,
    ):
        self._all_data = None
        self._changed = set()
        self.defaults = defaults.copy() if defaults else {}
        self._in_cm = False
        self.is_popup = is_popup
        self.name = name
        self.path = normalize_path(path)

    def __repr__(self) -> str:
        try:
            path = Path('~').joinpath(self.path.relative_to(Path.home())).as_posix()
        except ValueError:
            path = self.path.as_posix()

        # cfg_str = ', '.join(f'{k}={self.get(k)!r}' for k in ('auto_save', 'style'))
        cfg_str = ', '.join(f'{k}={getattr(self, k)!r}' for k in ('auto_save', 'style', 'is_popup'))
        return f'<{self.__class__.__name__}({self.name!r}, {path!r})[{cfg_str}]>'

    @property
    def _data(self) -> dict[str, dict[str, Any]]:
        if self._all_data is None:
            if self.path.is_file():
                with self.path.open('r', encoding='utf-8') as f:
                    self._all_data = json.load(f)
            else:
                self._all_data = {}

            self._changed = set()
        return self._all_data

    def _get_section(self, name: Optional[str]) -> dict[str, Any]:
        if name is None:
            try:
                return self.__data  # noqa
            except AttributeError:
                self.__data = data = {}
                return data

        all_data = self._data
        try:
            return all_data[name]
        except KeyError:
            all_data[name] = data = {}
            return data

    @property
    def data(self) -> dict[str, Any]:
        return self._get_section(self.name)

    @property
    def file_defaults(self) -> dict[str, Any]:
        return self._get_section(DEFAULT_SECTION)

    def __getitem__(self, key: str):
        try:
            return self.data[key]
        except KeyError:
            pass
        return self.__missing__(key)

    def __missing__(self, key: str):
        if defaults := self.defaults:
            try:
                return defaults[key]
            except KeyError:
                pass
        if defaults := self.file_defaults:
            try:
                return defaults[key]
            except KeyError:
                pass
        raise KeyError(key)

    def _get(self, key: str, default=_NotSet, type: Callable[[Any], T] = None) -> T:  # noqa
        try:
            value = self.data[key]
        except KeyError:
            if default is not _NotSet:
                return default
            value = self.__missing__(key)

        if type is None or (isclass(type) and isinstance(value, type)):  # noqa
            return value
        elif value is None and type is str:
            return value
        return type(value)

    def get(self, key: str, default=_NotSet, type: Callable[[Any], T] = None) -> T:  # noqa
        try:
            return self._get(key, default, type)
        except KeyError:
            return None

    def __setitem__(self, key: str, value: Any):
        try:
            old_value = self.data[key]
        except KeyError:
            pass
        else:
            if old_value == value:
                return

        self.data[key] = value
        self._changed.add(key)
        if self.auto_save:
            self.save()

    def __delitem__(self, key: str):
        del self.data[key]
        self._changed.add(key)
        if self.auto_save:
            self.save()

    def __enter__(self) -> WindowConfig:
        self._in_cm = True
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._in_cm = False
        if self.auto_save:
            self.save()

    def save(self, force: bool = False):
        if self._in_cm or self.name is None:
            return
        all_data = self._all_data
        if not all_data or not (self._changed or force):
            return

        changed = ', '.join(sorted(self._changed))
        suffix = f' for keys={changed}' if changed else ''
        log.debug(f'Saving state to {self.path}{suffix}')
        with self.path.open('w', encoding='utf-8') as f:
            json.dump(all_data, f, indent=4, sort_keys=True)

        self._changed = set()


class WindowConfigProperty:
    __slots__ = ('name',)

    def __set_name__(self, owner: Type[Window], name: str):
        self.name = name

    def __get__(self, window: Optional[Window], window_cls: Type[Window]) -> WindowConfig:
        try:
            return window.__dict__[self.name]
        except KeyError:
            pass
        try:
            name, path, defaults = window._config
        except TypeError:
            name = path = defaults = None

        window.__dict__[self.name] = config = WindowConfig(name, path, defaults, window.is_popup)
        return config


def normalize_path(path: Union[str, Path, None]) -> Path:
    if path is None:
        return Path(DEFAULT_PATH).expanduser()

    path = Path(path).expanduser()
    if path.parent.as_posix() == '.':  # Only a file name was provided
        path = Path(DEFAULT_DIR).expanduser().joinpath(path)
    if not path.suffix and not path.is_file():
        path /= DEFAULT_NAME

    return path
