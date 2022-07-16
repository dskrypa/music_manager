"""
Tkinter GUI Frame

:author: Doug Skrypa
"""

from __future__ import annotations

import logging
from tkinter import Frame as TkFrame, LabelFrame
from typing import TYPE_CHECKING, Optional, Union, Type, Literal, Any

from ..enums import Anchor
from ..pseudo_elements.row_container import RowContainer
from ..pseudo_elements.scroll import ScrollableFrame, ScrollableLabelFrame
from ..style import Style, StyleSpec
from ..window import CONTAINER_PARAMS
from .element import Element, ScrollableMixin

if TYPE_CHECKING:
    from ..typing import Layout, Bool
    from ..pseudo_elements.row import Row

__all__ = ['Frame']
log = logging.getLogger(__name__)

TkFrameType = Type[Union[TkFrame, LabelFrame]]
FrameMode = Literal['inner', 'outer', 'both']


class Frame(Element, RowContainer, ScrollableMixin):
    widget: Union[TkFrame, LabelFrame]
    inner_style: Optional[Style] = None

    def __init__(
        self,
        layout: Layout = None,
        title: str = None,
        *,
        anchor_title: Union[str, Anchor] = None,
        border: Bool = False,
        title_mode: FrameMode = 'outer',
        border_mode: FrameMode = 'outer',
        scroll_y: Bool = False,
        scroll_x: Bool = False,
        scroll_y_div: float = 2,
        scroll_x_div: float = 1,
        inner_style: StyleSpec = None,
        **kwargs,
    ):
        self.init_container(layout, **{k: kwargs.pop(k, None) for k in CONTAINER_PARAMS})
        Element.__init__(self, **kwargs)
        self.title = title
        self.title_mode = title_mode
        self.anchor_title = Anchor(anchor_title)
        self.border = border
        self.border_mode = border_mode
        self.scroll_y = scroll_y
        self.scroll_x = scroll_x
        self.scroll_y_div = scroll_y_div
        self.scroll_x_div = scroll_x_div
        if inner_style:
            self.inner_style = Style.get_style(inner_style)

    @property
    def tk_container(self) -> TkFrame:
        return self.widget

    def _prepare_pack_kwargs(self) -> dict[str, Any]:
        style = self.style
        outer_kw: dict[str, Any] = style.get_map('frame', bd='border_width', background='bg', relief='relief')
        if inner_style := self.inner_style:
            inner_kw = inner_style.get_map('frame', bd='border_width', background='bg', relief='relief')
        else:
            inner_style = style
            inner_kw = outer_kw.copy()

        if self.border:
            if self.border_mode in {'outer', 'both'}:
                outer_kw.setdefault('relief', 'groove')
                outer_kw.update(style.get_map('frame', highlightcolor='bg', highlightbackground='bg'))
            if self.border_mode in {'inner', 'both'}:
                inner_kw.setdefault('relief', 'groove')
                inner_kw.update(inner_style.get_map('frame', highlightcolor='bg', highlightbackground='bg'))

        if title := self.title:
            common = {'text': title}
            if (anchor := self.anchor_title) != Anchor.NONE:
                common['labelanchor'] = anchor.value

            if self.title_mode in {'outer', 'both'}:
                outer_kw.update(common)
                outer_kw.update(style.get_map('frame', foreground='fg', font='font'))
            if self.title_mode in {'inner', 'both'}:
                outer_kw['inner_cls'] = LabelFrame
                inner_kw.update(common)
                inner_kw.update(inner_style.get_map('frame', foreground='fg', font='font'))

        outer_kw['style'] = style
        outer_kw['inner_kwargs'] = inner_kw
        return outer_kw

    def pack_into(self, row: Row, column: int):
        kwargs = self._prepare_pack_kwargs()
        labeled = self.title_mode in {'outer', 'both'}
        outer_cls = ScrollableLabelFrame if labeled else ScrollableFrame
        self.frame = outer_frame = outer_cls(self.parent.frame, self.scroll_y, self.scroll_x, **kwargs)
        self.widget = inner_frame = outer_frame.inner_widget
        self.pack_rows()
        inner_frame.update()
        try:
            width, height = self.size
        except TypeError:
            width = inner_frame.winfo_reqwidth() // self.scroll_x_div
            height = inner_frame.winfo_reqheight() // self.scroll_y_div

        canvas = outer_frame.canvas
        canvas.configure(scrollregion=canvas.bbox('all'), width=width, height=height)
        self.pack_widget(widget=outer_frame)
