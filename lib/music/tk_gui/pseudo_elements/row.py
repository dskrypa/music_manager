"""
Tkinter GUI core Row class

:author: Doug Skrypa
"""

from __future__ import annotations

import logging
import tkinter.constants as tkc
from tkinter import Frame, Widget
from typing import TYPE_CHECKING, Optional, Union, Iterable

from ..style import Style
from ..utils import Anchor, Justify, Side, Inheritable

if TYPE_CHECKING:
    from ..elements import Element
    from ..typing import XY
    from ..window import Window
    from .row_container import RowContainer

__all__ = ['Row']
log = logging.getLogger(__name__)


class Row:
    frame: Optional[Frame] = None
    expand: Optional[bool] = None   # Set to True only for Column elements
    fill: Optional[bool] = None     # Changes for Column, Separator, StatusBar

    anchor_elements: Anchor = Inheritable(type=Anchor)
    text_justification: Justify = Inheritable(type=Justify)
    element_side: Side = Inheritable(type=Side)
    element_padding: XY = Inheritable()
    element_size: XY = Inheritable()
    style: Style = Inheritable()
    grid: bool = Inheritable()
    auto_size_text: bool = Inheritable()

    def __init__(self, parent: RowContainer, elements: Iterable[Element], num: int):
        self.num = num
        self.parent = parent
        self.elements = tuple(elements)
        self.id_ele_map = {ele.id: ele for ele in self.elements}

    def __getitem__(self, index_or_id: Union[int, str]):
        try:
            return self.id_ele_map[index_or_id]
        except KeyError:
            pass
        try:
            return self.elements[index_or_id]
        except (IndexError, TypeError):
            pass
        raise KeyError(f'Invalid column / index / element ID: {index_or_id!r}')

    def __contains__(self, item: Union[Element, Widget]) -> bool:
        if isinstance(item, Widget):
            if self.frame is item:
                return True
            for element in self.elements:
                if element.widget is item:
                    return True
            return False
        else:
            return item in self.elements

    @property
    def anchor(self):
        return self.anchor_elements.value

    @property
    def window(self) -> Window:
        return self.parent.window

    def pack(self, debug: bool = False):
        # log.debug(f'Packing row {self.num} in {self.parent=} {self.parent.tk_container=}')
        self.frame = frame = Frame(self.parent.tk_container)
        self.pack_elements(debug)
        anchor = self.anchor
        center = anchor == tkc.CENTER
        if (expand := self.expand) is None:
            expand = center
        if (fill := self.fill) is None:
            fill = tkc.BOTH if center else tkc.NONE
        # log.debug(f'Packing row with {center=}, {expand=}, {fill=}')
        frame.pack(side=tkc.TOP, anchor=anchor, padx=0, pady=0, expand=expand, fill=fill)
        if bg := self.style.base.bg.default:
            frame.configure(background=bg)

    def pack_elements(self, debug: bool = False):
        if debug:
            n_eles = len(self.elements)
            for i, ele in enumerate(self.elements):
                log.debug(f' > Packing element {i} / {n_eles}')
                try:
                    ele.pack_into_row(self, i)
                except Exception:
                    log.error(f'Encountered unexpected error packing element={ele} into row={self}', exc_info=True)
                    raise
        else:
            for i, ele in enumerate(self.elements):
                ele.pack_into_row(self, i)
