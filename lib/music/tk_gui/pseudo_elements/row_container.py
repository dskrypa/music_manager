"""
Tkinter GUI row container

:author: Doug Skrypa
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from itertools import count
from tkinter import Toplevel, Frame, Widget
from typing import TYPE_CHECKING, Optional, Union

from ..enums import Anchor, Justify, Side
from ..style import Style
from .row import Row

if TYPE_CHECKING:
    from ..elements.element import Element
    from ..typing import XY, Layout
    from ..window import Window

__all__ = ['RowContainer']
log = logging.getLogger(__name__)


class RowContainer(ABC):
    _counter = count()
    anchor_elements: Anchor
    text_justification: Justify
    element_side: Side
    element_padding: Optional[XY]
    element_size: Optional[XY]
    rows: list[Row]

    def __init__(
        self,
        layout: Layout = None,
        *,
        style: Style = None,
        grid: bool = False,
        anchor_elements: Union[str, Anchor] = None,
        text_justification: Union[str, Justify] = None,
        element_side: Union[str, Side] = None,
        element_padding: XY = None,
        element_size: XY = None,
    ):
        self._id = next(self._counter)
        self.style = Style.get_style(style)
        self.grid = grid
        self.init_container(layout, anchor_elements, text_justification, element_side, element_padding, element_size)

    def init_container(
        self,
        layout: Layout = None,
        anchor_elements: Union[str, Anchor] = None,
        text_justification: Union[str, Justify] = None,
        element_side: Union[str, Side] = None,
        element_padding: XY = None,
        element_size: XY = None,
    ):
        self.anchor_elements = Anchor(anchor_elements) if anchor_elements else Anchor.MID_CENTER
        self.text_justification = Justify(text_justification)
        self.element_side = Side(element_side) if element_side else Side.LEFT
        self.element_padding = element_padding
        self.element_size = element_size
        self.rows = [Row(self, row, i) for i, row in enumerate(layout)] if layout else []

    @property
    @abstractmethod
    def tk_container(self) -> Union[Frame, Toplevel]:
        raise NotImplementedError

    @property
    @abstractmethod
    def window(self) -> Window:
        raise NotImplementedError

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__}[{self._id}]>'

    def __getitem__(self, item: Union[str, tuple[int, int]]) -> Element:
        if isinstance(item, str) and '#' in item:
            for row in self.rows:
                try:
                    return row[item]
                except KeyError:
                    pass
        else:
            try:
                row, column = item
            except (ValueError, TypeError):
                pass
            else:
                try:
                    return self.rows[row][column]
                except (IndexError, TypeError, ValueError):
                    pass
        raise KeyError(f'Invalid element ID / (row, column) index: {item!r}')

    def __contains__(self, item: Union[Element, Widget]) -> bool:
        if item is self.tk_container:
            return True
        return any(item in row for row in self.rows)

    def pack_rows(self, debug: bool = False):
        # PySimpleGUI: PackFormIntoFrame(window, master, window)
        if debug:
            n_rows = len(self.rows)
            for i, row in enumerate(self.rows):
                log.debug(f'Packing row {i} / {n_rows}')
                row.pack(debug)
        else:
            for row in self.rows:
                row.pack()
