"""
Tkinter GUI Frames

:author: Doug Skrypa
"""

from __future__ import annotations

import logging
from abc import ABC
from tkinter import Frame as TkFrame, LabelFrame
from typing import TYPE_CHECKING, Optional, Union, Type, Literal, Any, Callable

from ..enums import Anchor
from ..pseudo_elements.row import RowBase
from ..pseudo_elements.row_container import RowContainer
from ..pseudo_elements.scroll import ScrollableFrame, ScrollableLabelFrame
from ..style import Style, StyleSpec
from ..utils import call_with_popped
from .element import Element, InteractiveMixin

if TYPE_CHECKING:
    from ..typing import Layout, Bool
    from ..pseudo_elements.row import Row

# __all__ = ['RowFrame', 'InteractiveRowFrame', 'Frame', 'InteractiveFrame', 'ScrollFrame']
__all__ = ['RowFrame', 'InteractiveRowFrame', 'ScrollFrame']
log = logging.getLogger(__name__)

TkFrameType = Type[Union[TkFrame, LabelFrame]]
FrameMode = Literal['inner', 'outer', 'both']
_Anchor = Union[str, Anchor]


class FrameMixin:
    widget: Union[TkFrame, LabelFrame]
    style: Style
    _style_config: dict[str, Any]
    allow_focus: bool
    border: Bool
    title: Optional[str]
    anchor_title: Anchor
    pack_rows: Callable
    pack_widget: Callable

    def init_frame(self, title: str = None, anchor_title: _Anchor = None, border: Bool = False):
        self.title = title
        self.anchor_title = Anchor(anchor_title)
        self.border = border

    def init_frame_from_kwargs(self, kwargs: dict[str, Any]):
        call_with_popped(self.init_frame, ('title', 'anchor_title', 'border'), kwargs)

    @property
    def tk_container(self) -> Union[TkFrame, LabelFrame]:
        return self.widget

    @property
    def style_config(self) -> dict[str, Any]:
        style = self.style
        config = {
            **style.get_map('frame', bd='border_width', background='bg', relief='relief'),
            **self._style_config,
        }
        if self.border:
            config.setdefault('relief', 'groove')
            config.update(style.get_map('frame', highlightcolor='bg', highlightbackground='bg'))
        if self.title:
            config.update(style.get_map('frame', foreground='fg', font='font'))

        return config

    def pack_into(self, row: Row, column: int):
        kwargs = self.style_config
        if title := self.title:
            kwargs['text'] = title
            if (anchor := self.anchor_title) != Anchor.NONE:
                kwargs['labelanchor'] = anchor.value
            frame_cls = LabelFrame
        else:
            frame_cls = TkFrame

        self.widget = frame_cls(row.frame, takefocus=int(self.allow_focus), **kwargs)
        self.pack_rows()
        self.pack_widget()


class RowFrame(FrameMixin, RowBase, Element, ABC):
    """
    A compound element that behaves both like a single :class:`.Element` and like a :class:`.Row` that contains other
    elements.  Compound elements that do not contain multiple rows can extend this instead of a Frame-like class that
    extends :class:`.RowContainer` to be lighter-weight since a RowContainer would contain at least one more additional
    nested Frame widget.
    """

    def __init__(self, **kwargs):
        self.init_frame_from_kwargs(kwargs)
        Element.__init__(self, **kwargs)

    @property
    def parent_rc(self) -> RowContainer:
        return self.parent.parent_rc  # self.parent is a Row

    @property
    def frame(self) -> Union[TkFrame, LabelFrame]:
        return self.widget

    def pack_rows(self, debug: Bool = False):
        self.pack_elements(debug)


class InteractiveRowFrame(InteractiveMixin, RowFrame, ABC):
    def __init__(self, **kwargs):
        self.init_interactive_from_kwargs(kwargs)
        super().__init__(**kwargs)


# class Frame(FrameMixin, Element, RowContainer):
#     def __init__(self, layout: Layout = None, **kwargs):
#         self.init_frame_from_kwargs(kwargs)
#         self.init_container_from_kwargs(layout, kwargs=kwargs)
#         Element.__init__(self, **kwargs)
#
#
# class InteractiveFrame(InteractiveMixin, Frame):
#     def __init__(self, layout: Layout = None, **kwargs):
#         self.init_interactive_from_kwargs(kwargs)
#         super().__init__(layout, **kwargs)


class ScrollFrame(Element, RowContainer):
    widget: Union[TkFrame, LabelFrame]
    inner_frame: Union[TkFrame, LabelFrame]
    inner_style: Optional[Style] = None

    def __init__(
        self,
        layout: Layout = None,
        title: str = None,
        *,
        anchor_title: _Anchor = None,
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

        inner_kw['takefocus'] = outer_kw['takefocus'] = int(self.allow_focus)
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
                # labelwidget: The widget to use as the label

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
