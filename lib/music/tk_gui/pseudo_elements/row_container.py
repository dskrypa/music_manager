"""
Tkinter GUI row container

:author: Doug Skrypa
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from functools import cached_property
from itertools import count
from tkinter import Toplevel, Frame, BaseWidget
from typing import TYPE_CHECKING, Optional, Union, Any, overload

from ..enums import Anchor, Justify, Side
from ..style import Style, StyleSpec
from ..utils import call_with_popped
from .row import Row, RowBase

if TYPE_CHECKING:
    from ..elements.element import ElementBase
    from ..typing import XY, Layout, Bool, TkContainer
    from ..window import Window
    from .scroll import ScrollableContainer, ScrollableToplevel

__all__ = ['RowContainer', 'CONTAINER_PARAMS']
log = logging.getLogger(__name__)

CONTAINER_PARAMS = {
    'anchor_elements', 'text_justification', 'element_side', 'element_padding', 'element_size',
    'scroll_y', 'scroll_x', 'scroll_y_div', 'scroll_x_div',
}


class RowContainer(ABC):
    _counter = count()
    ignore_grab: bool = False
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
        style: StyleSpec = None,
        anchor_elements: Union[str, Anchor] = None,
        text_justification: Union[str, Justify] = None,
        element_side: Union[str, Side] = None,
        element_padding: XY = None,
        element_size: XY = None,
        scroll_y: Bool = False,
        scroll_x: Bool = False,
        scroll_y_div: float = None,
        scroll_x_div: float = None,
    ):
        ...

    # endregion

    def __init__(self, layout: Layout = None, *, style: StyleSpec = None, **kwargs):
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
        scroll_y_div: float = None,
        scroll_x_div: float = None,
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

    def add_rows(self, layout: Layout):
        rows = self.rows
        for i, row in enumerate(layout, len(rows)):
            rows.append(Row(self, row, i))

    @property
    @abstractmethod
    def widget(self) -> Union[Frame, Toplevel, ScrollableToplevel]:
        raise NotImplementedError

    @property
    @abstractmethod
    def tk_container(self) -> Union[Frame, Toplevel]:
        raise NotImplementedError

    @property
    @abstractmethod
    def window(self) -> Window:
        raise NotImplementedError

    @cached_property
    def widgets(self) -> list[BaseWidget]:
        widgets = [w for row in self.rows for w in row.widgets]
        try:
            widgets.extend(self.widget.widgets)
        except AttributeError:
            widgets.append(self.widget)
        return widgets

    @cached_property
    def widget_element_map(self) -> dict[BaseWidget, Union[RowBase, ElementBase, RowContainer]]:
        widget_ele_map = {w: ele for row in self.rows for w, ele in row.widget_element_map.items()}
        try:
            widget_ele_map.update({widget: self for widget in self.widget.widgets})
        except AttributeError:
            widget_ele_map[self.widget] = self
        return widget_ele_map

    @cached_property
    def element_widgets_map(self) -> dict[Union[RowBase, ElementBase, RowContainer], list[BaseWidget]]:
        ele_widgets_map = {}
        for key, val in self.widget_element_map.items():
            try:
                ele_widgets_map[val].append(key)
            except KeyError:
                ele_widgets_map[val] = [key]

        return ele_widgets_map

    @cached_property
    def id_widget_map(self) -> dict[str, BaseWidget]:
        return {w._w: w for w in self.widget_element_map}  # noqa

    @cached_property
    def id_ele_map(self) -> dict[str, ElementBase]:
        id_ele_map = {}
        for ele in self.widget_element_map.values():
            try:
                id_ele_map[ele.id] = ele
            except AttributeError:
                pass
        return id_ele_map

    @cached_property
    def all_elements(self) -> list[Union[ElementBase, Row]]:
        from ..elements.element import ElementBase

        return [e for e in self.widget_element_map.values() if isinstance(e, (ElementBase, Row))]

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__}[{self._id}]>'

    def __getitem__(self, item: Union[str, BaseWidget, tuple[int, int]]) -> ElementBase:
        if isinstance(item, str):
            try:
                return self.id_ele_map[item]
            except KeyError:
                pass
            try:
                return self.widget_element_map[self.id_widget_map[item]]
            except KeyError:
                pass
        elif isinstance(item, BaseWidget):
            try:
                return self.widget_element_map[item]
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

    def __contains__(self, item: Union[str, ElementBase, BaseWidget]) -> bool:
        if isinstance(item, str):
            return item in self.id_ele_map or item in self.id_widget_map
        elif isinstance(item, BaseWidget):
            return item in self.widget_element_map
        return item in self.element_widgets_map

    def _scroll_divisors(self) -> tuple[float, float]:
        x_div, y_div = self.scroll_x_div, self.scroll_y_div
        if x_div is None:
            x_div = 1
        if y_div is None:
            y_div = 1.5
        return x_div, y_div

    def pack_container(self, outer: ScrollableContainer, inner: TkContainer, size: Optional[XY]):
        inner.update()
        try:
            width, height = size
        except TypeError:
            x_div, y_div = self._scroll_divisors()
            width = inner.winfo_reqwidth() // x_div
            height = inner.winfo_reqheight() // y_div

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
