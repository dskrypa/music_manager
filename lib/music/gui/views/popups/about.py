"""
View: About

:author: Doug Skrypa
"""

import inspect
import webbrowser
from pathlib import Path
from functools import cached_property
from typing import Any

from PySimpleGUI import Element, Text, OK

from ..base import event_handler, GuiView

__all__ = ['AboutView']


class AboutView(GuiView, view_name='about', primary=False):
    def __init__(self):
        super().__init__(binds={'<Escape>': 'Exit'})

    @cached_property
    def top_level_name(self):
        try:
            return Path(inspect.getsourcefile(inspect.stack()[-1][0])).stem
        except Exception as e:
            self.log.debug(f'Error determining top-level script info: {e}')
            return '[unknown]'

    @cached_property
    def top_level_globals(self):
        try:
            return inspect.stack()[-1].frame.f_globals
        except Exception as e:
            self.log.debug(f'Error determining top-level script info: {e}')
            return {}

    @cached_property
    def url(self):
        return self.top_level_globals.get('__url__', '[unknown]')

    @event_handler
    def link_clicked(self, event: str, data: dict[str, Any]):
        webbrowser.open(self.url)

    @event_handler(default=True)  # noqa
    def default(self, event: str, data: dict[str, Any]):
        raise StopIteration

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
