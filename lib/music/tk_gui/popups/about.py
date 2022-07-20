"""
Tkinter GUI popup: About

:author: Doug Skrypa
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..elements import Text, Link
from ..elements.buttons import OK
from ..utils import ProgramMetadata
from .base import Popup

if TYPE_CHECKING:
    from ..typing import Layout

__all__ = ['AboutPopup']


class AboutPopup(Popup):
    def __init__(self, data: dict[str, str] = None, title: str = None, **kwargs):
        kwargs.setdefault('bind_esc', True)
        kwargs.setdefault('keep_on_top', True)
        super().__init__(title=title or 'About', **kwargs)
        self.about_data = data

    def get_about_data(self):
        if self.about_data:
            return {k.title() if k.endswith(':') else f'{k.title()}:': v for k, v in self.about_data.items()}

        meta = ProgramMetadata()
        return {'Program:': meta.name, 'Author:': meta.author, 'Version:': meta.version, 'Project URL:': meta.url}

    def get_layout(self) -> Layout:
        data = self.get_about_data()
        size = (max(map(len, data)), 1)
        layout = [[Text(key, size=size), (Link if 'url' in key.lower() else Text)(val)] for key, val in data.items()]
        layout.append([OK()])  # noqa
        return layout
