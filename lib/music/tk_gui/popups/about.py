"""
Tkinter GUI popup: About

:author: Doug Skrypa
"""

from __future__ import annotations

import logging
import sys
from inspect import stack
from pathlib import Path
from functools import cached_property
from typing import TYPE_CHECKING

from ..elements import Text, Link
from ..elements.buttons import OK
from .base import Popup

if TYPE_CHECKING:
    from ..typing import Layout

__all__ = ['AboutPopup']
log = logging.getLogger(__name__)


class AboutPopup(Popup):
    def __init__(self, data: dict[str, str] = None, title: str = None, **kwargs):
        kwargs.setdefault('bind_esc', True)
        kwargs.setdefault('keep_on_top', True)
        super().__init__(title or 'About', **kwargs)
        self.about_data = data

    def get_about_data(self):
        if self.about_data:
            return {k.title() if k.endswith(':') else f'{k.title()}:': v for k, v in self.about_data.items()}

        g = self.top_level_globals.get
        name, url, d = self.top_level_name, self.url, '[unknown]'
        return {'Program:': name, 'Author:': g('__author__', d), 'Version:': g('__version__', d), 'Project URL:': url}

    def get_layout(self) -> Layout:
        data = self.get_about_data()
        size = (max(map(len, data)), 1)
        layout = [[Text(key, size=size), (Link if 'url' in key.lower() else Text)(val)] for key, val in data.items()]
        layout.append([OK()])  # noqa
        return layout

    def _get_top_level(self):
        _stack = stack()
        top_level_frame_info = _stack[-1]
        path = Path(top_level_frame_info.filename)
        g = top_level_frame_info.frame.f_globals
        if (installed_via_setup := 'load_entry_point' in g and 'main' not in g) or path.stem == 'runpy':
            for level in reversed(_stack[:-1]):
                g = level.frame.f_globals
                if any(k in g for k in ('__author_email__', '__version__', '__url__')):
                    return installed_via_setup, g, Path(level.filename)

        return installed_via_setup, g, path

    @cached_property
    def top_level(self):
        try:
            return self._get_top_level()
        except Exception as e:  # noqa
            log.debug(f'Error determining top-level script info: {e}')
            if sys.argv:
                path = Path(sys.argv[0])
            else:
                path = Path.cwd().joinpath('[unknown]')
            return False, {}, path

    @cached_property
    def top_level_globals(self):
        return self.top_level[1]

    @cached_property
    def top_level_name(self):
        installed_via_setup, g, path = self.top_level
        if installed_via_setup and path.name.endswith('-script.py'):
            if sys.argv:
                path = path.with_name(Path(sys.argv[0]).name)
            else:
                path = path.with_name(path.stem[:-7] + '.py')

        return path.stem

    @cached_property
    def url(self):
        return self.top_level_globals.get('__url__', '[unknown]')
