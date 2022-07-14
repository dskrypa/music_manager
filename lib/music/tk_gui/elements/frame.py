"""
Tkinter GUI Frame

:author: Doug Skrypa
"""

from __future__ import annotations

import logging
import tkinter.constants as tkc
from tkinter import Frame as TkFrame, LabelFrame, Canvas, Widget, Event
from typing import TYPE_CHECKING, Optional, Union, Iterable, Type

from ..enums import Anchor, Justify, Side
from ..pseudo_elements.row_container import RowContainer
from ..pseudo_elements.scroll import add_scroll_bar
from ..style import Style
from ..window import Window, CONTAINER_PARAMS, ON_WINDOWS
from .element import Element, ElementBase, ScrollableMixin

if TYPE_CHECKING:
    from tkinter.ttk import Scrollbar
    from ..typing import Layout, Bool
    from ..pseudo_elements.row import Row

__all__ = ['Frame']
log = logging.getLogger(__name__)

TkFrameType = Type[Union[TkFrame, LabelFrame]]


class ScrollableFrame(TkFrame):
    _y_bind, _x_bind = ('<MouseWheel>', 'Shift-MouseWheel') if ON_WINDOWS else ('<4>', '<5>')
    widget: Canvas
    scroll_bar_y: Optional[Scrollbar] = None
    scroll_bar_x: Optional[Scrollbar] = None

    def __init__(
        self, parent: Frame, scroll_y: Bool = False, scroll_x: Bool = False, inner_cls: TkFrameType = TkFrame, **kwargs
    ):
        TkFrame.__init__(self, parent.parent.frame, borderwidth=0, highlightthickness=0)
        self.canvas = canvas = Canvas(self, borderwidth=0, highlightthickness=0)
        style = parent.style
        if scroll_x:
            self.scroll_bar_x = add_scroll_bar(self, canvas, 'x', style, {'expand': 'false'})
        if scroll_y:
            self.scroll_bar_y = add_scroll_bar(self, canvas, 'y', style, {'fill': 'both', 'expand': True})

        # canvas.pack(side='left', fill='both', expand=True, padx=0, pady=0)
        canvas.pack(side='left', fill='both', expand=True)
        canvas.xview_moveto(0)
        canvas.yview_moveto(0)
        self.inner_frame = inner_frame = inner_cls(canvas, borderwidth=0, highlightthickness=0)
        self.inner_frame_id = canvas.create_window(0, 0, window=inner_frame, anchor='nw')

        if scroll_y or scroll_x:
            # TODO: If mouse is inside a nested scrollable widget, don't scroll this one
            canvas.bind('<Enter>', self.hook_mouse_scroll)
            canvas.bind('<Leave>', self.unhook_mouse_scroll)
            self.bind('<Configure>', self.set_scroll_region)

    def resize_frame(self, event: Event):
        self.widget.itemconfigure(self.inner_frame_id, width=event.width, height=event.height)

    def hook_mouse_scroll(self, event: Event = None):
        canvas = self.canvas
        canvas.bind_all(self._y_bind, self.scroll_y, add='+')
        canvas.bind_all(self._x_bind, self.scroll_x, add='+')

    def unhook_mouse_scroll(self, event: Event = None):
        canvas = self.canvas
        canvas.unbind_all(self._y_bind)
        canvas.unbind_all(self._x_bind)

    def scroll_y(self, event: Event = None):
        canvas = self.canvas
        if canvas.yview() == (0, 1):
            return
        elif event.num == 5 or event.delta < 0:
            canvas.yview_scroll(4, 'units')
        elif event.num == 4 or event.delta > 0:
            canvas.yview_scroll(-4, 'units')

    def scroll_x(self, event: Event = None):
        canvas = self.canvas
        if event.num == 5 or event.delta < 0:
            canvas.xview_scroll(4, 'units')
        elif event.num == 4 or event.delta > 0:
            canvas.xview_scroll(-4, 'units')

    def set_scroll_region(self, event: Event = None):
        canvas = self.canvas
        bbox = canvas.bbox('all')
        if canvas['scrollregion'] != '{} {} {} {}'.format(*bbox):
            # log.debug(f'Updating scroll region to {bbox=} != {canvas["scrollregion"]=} for {self}')
            canvas.configure(scrollregion=bbox)


class Frame(Element, RowContainer, ScrollableMixin):
    widget: Union[TkFrame, LabelFrame]

    def __init__(
        self,
        layout: Layout = None,
        title: str = None,
        *,
        anchor_title: Union[str, Anchor] = None,
        border: Bool = False,
        scroll_y: Bool = False,
        scroll_x: Bool = False,
        **kwargs,
    ):
        self.init_container(layout, **{k: kwargs.pop(k, None) for k in CONTAINER_PARAMS})
        Element.__init__(self, **kwargs)
        self.title = title
        self.anchor_title = Anchor(anchor_title)
        self.border = border  # TODO: relief='groove' when True
        self.scroll_y = scroll_y
        self.scroll_x = scroll_x

    @property
    def tk_container(self) -> TkFrame:
        return self.widget

    def pack_into(self, row: Row, column: int):
        style = self.style
        kwargs = {
            # 'highlightthickness': 0,
            # **style.get_map('frame', bd='border_width', background='bg', relief='relief'),
        }
        # if self.border:
        #     kwargs.setdefault('relief', 'groove')  # noqa
        # if title := self.title:
        #     kwargs['inner_cls'] = LabelFrame
        #     kwargs['text'] = title
        #     kwargs.update(style.get_map('frame', foreground='fg', font='font'))
        #     if (anchor := self.anchor_title) != Anchor.NONE:
        #         kwargs['labelanchor'] = anchor.value

        # try:
        #     kwargs['width'], kwargs['height'] = self.size
        # except TypeError:
        #     pass

        log.info(f'Creating frame with {kwargs=}')

        self.frame = outer_frame = ScrollableFrame(self, self.scroll_y, self.scroll_x, **kwargs)
        self.widget = inner_frame = outer_frame.inner_frame
        canvas = outer_frame.canvas

        """
        size_subsample_width=1,
        size_subsample_height=2,
        """
        self.pack_rows()
        inner_frame.update()

        req_width = inner_frame.winfo_reqwidth()
        req_height = inner_frame.winfo_reqheight()
        # print(f'Required {req_width=}, {req_height=}')
        # outer_frame.configure(width=req_width, height=100)
        canvas.configure(scrollregion=canvas.bbox('all'), width=req_width, height=req_height // 2)
        # outer_frame.configure(height=100)

        # if self.size:
        #     width, height = self.size
        #     # canvas.configure(width=width, height=height)
        #     # outer_frame.configure(width=width, height=height)
        #     outer_frame.configure(width=width, height=height)
        # else:
        #     width = inner_frame.winfo_reqwidth()
        #     height = inner_frame.winfo_reqheight() // 2
        #     print(f'Required {width=}, {height=}')
        #     # canvas.configure(width=width, height=height)
        # canvas.configure(height=height)

        # self.pack_widget()
        # self.pack_widget(padx=0, pady=0)

        # self.pack_widget(widget=frame)
        # frame.pack(anchor=self.anchor.value, side=self.side.value, expand=True, fill='both', **self.pad_kw)
        # print(f'{self.anchor=}, {self.side=}')
        outer_frame.pack(anchor=self.anchor.value, side=self.side.value, expand=False, fill='none', **self.pad_kw)
        # outer_frame.pack(anchor=self.anchor.value, side=self.side.value, expand=True, fill='both', **self.pad_kw)
