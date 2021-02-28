"""
Music Manager GUI state

:author: Doug Skrypa
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any

from ds_tools.fs.paths import get_user_cache_dir

__all__ = ['GuiState']
log = logging.getLogger(__name__)


class GuiState:
    def __init__(self):
        self._path = Path(get_user_cache_dir('music_manager')).joinpath('gui_state.json')
        self._state = None
        self._changed = None

    @property
    def state(self) -> Dict[str, Any]:
        if self._state is None:
            if self._path.is_file():
                with self._path.open('r', encoding='utf-8') as f:
                    self._state = json.load(f)
            else:
                self._state = {}

            self._changed = False
        return self._state

    def __getitem__(self, key: str):
        return self.state[key]

    def get(self, key: str, default=None):
        return self.state.get(key, default)

    def __setitem__(self, key: str, value: Any):
        self.state[key] = value
        self._changed = True

    def save(self, force: bool = False):
        if self._state and (self._changed or force):
            log.debug(f'Saving state to {self._path}')
            with self._path.open('w', encoding='utf-8') as f:
                json.dump(self._state, f)

            self._changed = False
