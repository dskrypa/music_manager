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
from .element import Element

if TYPE_CHECKING:
    from ..typing import Layout, Bool
    from ..pseudo_elements.row import Row

__all__ = ['Frame']
log = logging.getLogger(__name__)

TkFrameType = Type[Union[TkFrame, LabelFrame]]
FrameMode = Literal['inner', 'outer', 'both']


class Frame(Element, RowContainer):
    widget: Union[TkFrame, LabelFrame]
    inner_frame: Union[TkFrame, LabelFrame]
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
        inner_style: StyleSpec = None,
        **kwargs,
    ):
        self.init_container_from_kwargs(layout, kwargs=kwargs)
        Element.__init__(self, **kwargs)
        self.title = title
        self.title_mode = title_mode
        self.anchor_title = Anchor(anchor_title)
        self.border = border
        self.border_mode = border_mode
        if inner_style:
            self.inner_style = Style.get_style(inner_style)

    @property
    def tk_container(self) -> TkFrame:
        return self.inner_frame

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
        self.widget = outer_frame = outer_cls(self.parent.frame, self.scroll_y, self.scroll_x, **kwargs)
        self.inner_frame = inner_frame = outer_frame.inner_widget
        self.pack_rows()
        self.pack_container(outer_frame, inner_frame, self.size)
        self.pack_widget()
