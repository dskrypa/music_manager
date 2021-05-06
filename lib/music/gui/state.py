"""
Music Manager GUI state

:author: Doug Skrypa
"""

import json
import logging
from pathlib import Path
from typing import Any, Type, Mapping

from ds_tools.fs.paths import get_user_cache_dir

__all__ = ['GuiState']
log = logging.getLogger(__name__)
_NotSet = object()


class GuiState:
    def __init__(self, auto_save: bool = False, defaults: Mapping[str, Any] = None):
        self._path = Path(get_user_cache_dir('music_manager')).joinpath('gui_state.json')
        self._state = None
        self._changed = None
        self._defaults = defaults
        self.auto_save = auto_save

    @property
    def state(self) -> dict[str, Any]:
        if self._state is None:
            if self._path.is_file():
                with self._path.open('r', encoding='utf-8') as f:
                    self._state = json.load(f)
            else:
                self._state = {}

            self._changed = False
        return self._state

    def __getitem__(self, key: str):
        try:
            return self.state[key]
        except KeyError:
            if not self._defaults:
                raise
        return self._defaults[key]

    def get(self, key: str, default=_NotSet, type: Type = None):  # noqa
        try:
            value = self.state[key]
        except KeyError:
            if default is _NotSet:
                return self._defaults.get(key) if self._defaults else None
            return default
        else:
            return type(value) if type is not None and not isinstance(value, type) else value

    def __setitem__(self, key: str, value: Any):
        self.state[key] = value
        self._changed = True
        if self.auto_save:
            self.save()

    def save(self, force: bool = False):
        if self._state and (self._changed or force):
            log.debug(f'Saving state to {self._path}')
            with self._path.open('w', encoding='utf-8') as f:
                json.dump(self._state, f, indent=4, sort_keys=True)

            self._changed = False
