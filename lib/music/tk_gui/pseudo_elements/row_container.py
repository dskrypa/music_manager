"""
Tkinter GUI row container

:author: Doug Skrypa
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from itertools import count
from tkinter import Toplevel, Frame, Widget, Misc
from typing import TYPE_CHECKING, Optional, Union, Any, overload

from ..enums import Anchor, Justify, Side
from ..style import Style
from ..utils import call_with_popped
from .row import Row

if TYPE_CHECKING:
    from ..elements.element import Element
    from ..typing import XY, Layout, Bool, TkContainer
    from ..window import Window
    from .scroll import ScrollableContainer

__all__ = ['RowContainer', 'CONTAINER_PARAMS']
log = logging.getLogger(__name__)

CONTAINER_PARAMS = {
    'anchor_elements', 'text_justification', 'element_side', 'element_padding', 'element_size',
    'scroll_y', 'scroll_x', 'scroll_y_div', 'scroll_x_div',
}


class RowContainer(ABC):
    _counter = count()
    scroll_y: Bool = False
    scroll_x: Bool = False
    scroll_y_div: float = 2
    scroll_x_div: float = 1
    anchor_elements: Anchor
    text_justification: Justify
    element_side: Side
    element_padding: Optional[XY]
    element_size: Optional[XY]
    rows: list[Row]

    # region Init Overload

    @overload
    def __init__(
        self,
        layout: Layout = None,
        *,
        style: Style = None,
        anchor_elements: Union[str, Anchor] = None,
        text_justification: Union[str, Justify] = None,
        element_side: Union[str, Side] = None,
        element_padding: XY = None,
        element_size: XY = None,
        scroll_y: Bool = False,
        scroll_x: Bool = False,
        scroll_y_div: float = 2,
        scroll_x_div: float = 1,
    ):
        ...

    # endregion

    def __init__(self, layout: Layout = None, *, style: Style = None, **kwargs):
        self._id = next(self._counter)
        self.style = Style.get_style(style)
        self.init_container(layout, **kwargs)

    def init_container_from_kwargs(self, *args, kwargs: dict[str, Any]):
        call_with_popped(self.init_container, CONTAINER_PARAMS, kwargs, args)

    def init_container(
        self,
        layout: Layout = None,
        anchor_elements: Union[str, Anchor] = None,
        text_justification: Union[str, Justify] = None,
        element_side: Union[str, Side] = None,
        element_padding: XY = None,
        element_size: XY = None,
        scroll_y: Bool = False,
        scroll_x: Bool = False,
        scroll_y_div: float = 2,
        scroll_x_div: float = 1,
    ):
        self.anchor_elements = Anchor(anchor_elements)
        self.text_justification = Justify(text_justification)
        self.element_side = Side(element_side) if element_side else Side.LEFT
        self.element_padding = element_padding
        self.element_size = element_size
        self.rows = [Row(self, row, i) for i, row in enumerate(layout)] if layout else []
        self.scroll_y = scroll_y
        self.scroll_x = scroll_x
        self.scroll_y_div = scroll_y_div
        self.scroll_x_div = scroll_x_div

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

    def __contains__(self, item: Union[Element, Widget, Misc]) -> bool:
        if item is self.tk_container:
            return True
        return any(item in row for row in self.rows)

    def pack_container(self, outer: ScrollableContainer, inner: TkContainer, size: Optional[XY]):
        inner.update()
        try:
            width, height = size
        except TypeError:
            width = inner.winfo_reqwidth() // self.scroll_x_div
            height = inner.winfo_reqheight() // self.scroll_y_div

        canvas = outer.canvas
        canvas.configure(scrollregion=canvas.bbox('all'), width=width, height=height)

    def pack_rows(self, debug: Bool = False):
        # PySimpleGUI: PackFormIntoFrame(window, master, window)
        if debug:
            n_rows = len(self.rows)
            for i, row in enumerate(self.rows):
                log.debug(f'Packing row {i} / {n_rows}')
                row.pack(debug)
        else:
            for row in self.rows:
                row.pack()
