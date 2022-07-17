"""
Input GUI elements

:author: Doug Skrypa
"""

from __future__ import annotations

import logging
import tkinter.constants as tkc
from tkinter import TclError, Entry, StringVar
from tkinter.ttk import Separator as TtkSeparator
from typing import TYPE_CHECKING, Optional, Union, Any

from .element import ElementBase

if TYPE_CHECKING:
    from ..pseudo_elements import Row
    from ..style import StyleSpec
    from ..typing import XY, Layout, Bool, TkFill, Orientation

__all__ = ['Separator', 'HorizontalSeparator', 'VerticalSeparator']
log = logging.getLogger(__name__)


class Separator(ElementBase):
    def __init__(self, orientation: Orientation, **kwargs):
        super().__init__(**kwargs)
        self.orientation = orientation

    def pack_into(self, row: Row, column: int):
        style = self.style
        name, ttk_style = style.make_ttk_style('.Line.TSeparator')
        ttk_style.configure(name, background=style.separator.bg.default)
        self.widget = TtkSeparator(row.frame, orient=self.orientation, style=name)
        fill, expand = (tkc.X, True) if self.orientation == tkc.HORIZONTAL else (tkc.Y, False)
        self.pack_widget(fill=fill, expand=expand)


class HorizontalSeparator(Separator):
    def __init__(self, **kwargs):
        super().__init__(tkc.HORIZONTAL, **kwargs)


class VerticalSeparator(Separator):
    def __init__(self, **kwargs):
        super().__init__(tkc.VERTICAL, **kwargs)

