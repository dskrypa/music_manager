"""
Tkinter GUI core Row and Element classes

:author: Doug Skrypa
"""

from __future__ import annotations

import logging
import tkinter.constants as tkc
from tkinter import Frame
from typing import TYPE_CHECKING, Optional, Iterable

from ..style import Style
from ..utils import Anchor, Inheritable, XY

if TYPE_CHECKING:
    from ..core import RowContainer
    from ..elements import Element

__all__ = ['Row']
log = logging.getLogger(__name__)


class Row:
    frame: Optional[Frame] = None
    expand: Optional[bool] = None   # Set to True only for Column elements
    fill: Optional[bool] = None     # Changes for Column, Separator, StatusBar

    element_justification = Inheritable(type=Anchor)    # type: Anchor
    element_padding = Inheritable()                     # type: XY
    element_size = Inheritable()                        # type: XY
    style = Inheritable()                               # type: Style
    auto_size_text = Inheritable()                      # type: bool

    def __init__(self, parent: RowContainer, elements: Iterable[Element]):
        self.parent = parent
        self.elements = list(elements)
        # for ele in self.elements:
        #     ele.parent = self

    def __getitem__(self, index: int):
        return self.elements[index]

    @property
    def anchor(self):
        return self.element_justification.value

    def pack(self):
        self.frame = frame = Frame(self.parent.tk_container)
        for ele in self.elements:
            ele.pack_into_row(self)
        anchor = self.anchor
        center = anchor == tkc.CENTER
        if (expand := self.expand) is None:
            expand = center
        if (fill := self.fill) is None:
            fill = tkc.BOTH if center else tkc.NONE
        # log.debug(f'Packing row with {center=}, {expand=}, {fill=}')
        frame.pack(side=tkc.TOP, anchor=anchor, padx=0, pady=0, expand=expand, fill=fill)
        if bg := self.style.bg.default:
            frame.configure(background=bg)
