"""
View: About

:author: Doug Skrypa
"""

import inspect
import sys
import webbrowser
from pathlib import Path
from functools import cached_property
from typing import Any

from PySimpleGUI import Element, Text, OK

from ..base_view import event_handler
from .base import BasePopup

__all__ = ['AboutView']


class AboutView(BasePopup, view_name='about', primary=False):
    def __init__(self):
        super().__init__(binds={'<Escape>': 'Exit'})

    @cached_property
    def top_level_name(self):
        try:
            top_level_frame_info = inspect.stack()[-1]
            g = top_level_frame_info.frame.f_globals
            installed_via_setup = 'load_entry_point' in g and 'main' not in g
            path = Path(inspect.getsourcefile(top_level_frame_info[0]))
            if installed_via_setup and path.name.endswith('-script.py'):
                if sys.argv:
                    path = path.with_name(Path(sys.argv[0]).name)
                else:
                    path = path.with_name(path.stem[:-7] + '.py')
            return path.stem
        except Exception as e:
            self.log.debug(f'Error determining top-level script info: {e}')
            return '[unknown]'

    @cached_property
    def top_level_globals(self):
        try:
            stack = inspect.stack()
            g = stack[-1].frame.f_globals
            if 'load_entry_point' in g and 'main' not in g:
                for level in reversed(stack[:-1]):
                    g = level.frame.f_globals
                    if any(k in g for k in ('__author_email__', '__version__', '__url__')):
                        break
            return g
        except Exception as e:
            self.log.debug(f'Error determining top-level script info: {e}')
            return {}

    @cached_property
    def url(self):
        return self.top_level_globals.get('__url__', '[unknown]')

    @event_handler
    def link_clicked(self, event: str, data: dict[str, Any]):
        webbrowser.open(self.url)

    def get_render_args(self) -> tuple[list[list[Element]], dict[str, Any]]:
        if self.url != '[unknown]':
            link = Text(self.url, enable_events=True, key='link_clicked', text_color='blue')
        else:
            link = Text(self.url)

        layout = [
            [Text('Program:', size=(12, 1)), Text(self.top_level_name)],
            [Text('Author:', size=(12, 1)), Text(self.top_level_globals.get('__author__', '[unknown]'))],
            [Text('Version:', size=(12, 1)), Text(self.top_level_globals.get('__version__', '[unknown]'))],
            [Text('Project URL:', size=(12, 1)), link],
            [OK()],
        ]
        return layout, {'title': 'About'}
