"""
Music Manager GUI state

:author: Doug Skrypa
"""

import json
import logging
from pathlib import Path
from typing import Any, Type, Union

__all__ = ['GuiConfig']
log = logging.getLogger(__name__)
_NotSet = object()
DEFAULT_PATH = '~/.config/music_manager/gui_config.json'


class GuiConfig:
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
        if self._data and (self._changed or force):
            suffix = ' for keys={}'.format(', '.join(sorted(self._changed))) if self._changed else ''
            log.debug(f'Saving state to {self._path}{suffix}')
            with self._path.open('w', encoding='utf-8') as f:
                json.dump(self._data, f, indent=4, sort_keys=True)

            self._changed = set()
