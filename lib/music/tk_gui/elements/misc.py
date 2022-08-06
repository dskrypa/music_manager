"""
Misc GUI elements

:author: Doug Skrypa
"""

from __future__ import annotations

import tkinter.constants as tkc
from tkinter.ttk import Sizegrip
from typing import TYPE_CHECKING, Union

from .element import ElementBase

if TYPE_CHECKING:
    from ..enums import Side
    from ..pseudo_elements import Row

__all__ = ['SizeGrip']


class SizeGrip(ElementBase):
    """Visual indicator that resizing is possible, located at the bottom-right corner of a window"""
    widget: Sizegrip

    def __init__(self, side: Union[str, Side] = tkc.BOTTOM, **kwargs):
        super().__init__(side=side, **kwargs)

    def pack_into(self, row: Row, column: int):
        style = self.style
        name, ttk_style = style.make_ttk_style('.Sizegrip.TSizegrip')
        ttk_style.configure(name, background=style.base.bg.default)
        self.widget = Sizegrip(row.frame, style=name, takefocus=int(self.allow_focus))
        self.pack_widget(fill=tkc.X, expand=True, anchor=tkc.SE)
