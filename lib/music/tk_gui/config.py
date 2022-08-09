"""
Music Manager GUI config

:author: Doug Skrypa
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Type, Union, Optional

from ..__version__ import __title__

if TYPE_CHECKING:
    from .window import Window

__all__ = ['WindowConfig', 'WindowConfigProperty']
log = logging.getLogger(__name__)

_NotSet = object()
DEFAULT_DIR = '~/.config'
DEFAULT_NAME = 'gui_config.json'
DEFAULT_PATH = f'{DEFAULT_DIR}/{__title__}/{DEFAULT_NAME}'
DEFAULT_SECTION = '__default__'


class ConfigItem:
    __slots__ = ('name', 'default')

    def __init__(self, default):
        self.default = default

    def __set_name__(self, owner: Type[WindowConfig], name: str):
        self.name = name

    def __get__(self, instance: Optional[WindowConfig], owner: Type[WindowConfig]):
        try:
            return instance[self.name]
        except KeyError:
            return self.default

    def __set__(self, instance: WindowConfig, value):
        if value is not _NotSet:
            instance[self.name] = value

    def __delete__(self, instance: WindowConfig):
        del instance[self.name]


class WindowConfig:
    auto_save = ConfigItem(True)
    remember_size = ConfigItem(True)
    remember_position = ConfigItem(True)
    style = ConfigItem(None)

    def __init__(
        self,
        name: Optional[str],
        path: Union[str, Path] = None,
        defaults: dict[str, Any] = None,
        auto_save: bool = _NotSet,
    ):
        self.name = name or DEFAULT_SECTION
        self.path = normalize_path(path)
        self.auto_save = auto_save
        self._all_data = None
        self._changed = set()
        self.defaults = defaults.copy() if defaults else {}

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

    def _get_section(self, name: str) -> dict[str, Any]:
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

    def get(self, key: str, default=_NotSet, type: Type = None):  # noqa
        try:
            value = self.data[key]
        except KeyError:
            if default is not _NotSet:
                return default
            try:
                value = self.__missing__(key)
            except KeyError:
                return None

        if type is None or isinstance(value, type):
            return value
        return type(value)

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

    def save(self, force: bool = False):
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
    def __get__(self, window: Optional[Window], window_cls: Type[Window]) -> WindowConfig:
        try:
            name, path, defaults = window._config
        except TypeError:
            name = path = defaults = None
            auto_save = False
        else:
            auto_save = window.is_popup
        return WindowConfig(name, path, defaults, auto_save)


class GuiConfig:
    # TODO: Remove
    def __init__(self, path: Union[str, Path] = DEFAULT_PATH, auto_save: bool = False, defaults: dict[str, Any] = None):
        self.path = path
        self._data = None
        self._changed = set()
        self.defaults = defaults.copy() if defaults else {}
        self.auto_save = auto_save

    @property
    def path(self) -> Path:
        return self._path

    @path.setter
    def path(self, path: Union[str, Path]):
        path = Path(path).expanduser()
        if path.parent.as_posix() == '.':  # If only a file name was provided
            path = Path(DEFAULT_PATH).expanduser().parent.joinpath(path)
        if not path.parent.exists():
            path.parent.mkdir(parents=True)
        self._path = path

    @property
    def data(self) -> dict[str, Any]:
        if self._data is None:
            if self._path.is_file():
                with self._path.open('r', encoding='utf-8') as f:
                    self._data = json.load(f)
            else:
                self._data = {}

            self._changed = set()
        return self._data

    def __getitem__(self, key: str):
        try:
            return self.data[key]
        except KeyError:
            if not self.defaults:
                raise
        return self.defaults[key]

    def get(self, key: str, default=_NotSet, type: Type = None):  # noqa
        try:
            value = self.data[key]
        except KeyError:
            if default is _NotSet:
                return self.defaults.get(key) if self.defaults else None
            return default
        else:
            return type(value) if type is not None and not isinstance(value, type) else value

    def __setitem__(self, key: str, value: Any):
        self.data[key] = value
        self._changed.add(key)
        if self.auto_save:
            self.save()

    def save(self, force: bool = False):
        if not self._data or not (self._changed or force):
            return

        changed = ', '.join(sorted(self._changed))
        suffix = f' for keys={changed}' if changed else ''
        log.debug(f'Saving state to {self._path}{suffix}')
        with self._path.open('w', encoding='utf-8') as f:
            json.dump(self._data, f, indent=4, sort_keys=True)

        self._changed = set()


def normalize_path(path: Union[str, Path, None]) -> Path:
    if path is None:
        return Path(DEFAULT_PATH).expanduser()

    path = Path(path).expanduser()
    if path.parent.as_posix() == '.':  # Only a file name was provided
        path = Path(DEFAULT_DIR).expanduser().joinpath(path)
    if not path.suffix and not path.is_file():
        path /= DEFAULT_NAME

    return path
