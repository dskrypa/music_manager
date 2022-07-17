"""
Input GUI elements

:author: Doug Skrypa
"""

from __future__ import annotations

import logging
import tkinter.constants as tkc
from tkinter.ttk import Separator as TtkSeparator, Progressbar
from typing import TYPE_CHECKING, Iterable, Iterator

from .element import ElementBase, Element

if TYPE_CHECKING:
    from ..pseudo_elements import Row
    from ..typing import Bool, Orientation, T

__all__ = ['Separator', 'HorizontalSeparator', 'VerticalSeparator', 'ProgressBar']
log = logging.getLogger(__name__)

# region Separators


class Separator(ElementBase):
    widget: TtkSeparator

    def __init__(self, orientation: Orientation, **kwargs):
        super().__init__(**kwargs)
        self.orientation = orientation

    def pack_into(self, row: Row, column: int):
        style = self.style
        name, ttk_style = style.make_ttk_style('.Line.TSeparator')
        ttk_style.configure(name, background=style.separator.bg.default)
        self.widget = TtkSeparator(row.frame, orient=self.orientation, style=name)
        fill, expand = (tkc.X, True) if self.orientation == tkc.HORIZONTAL else (tkc.Y, False)
        self.pack_widget(fill=fill, expand=expand)


class HorizontalSeparator(Separator):
    def __init__(self, **kwargs):
        super().__init__(tkc.HORIZONTAL, **kwargs)


class VerticalSeparator(Separator):
    def __init__(self, **kwargs):
        super().__init__(tkc.VERTICAL, **kwargs)


# endregion


class ProgressBar(Element):
    widget: Progressbar

    def __init__(
        self,
        max_value: int,
        default: int = 0,
        orientation: Orientation = tkc.HORIZONTAL,
        max_on_exit: Bool = True,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.max_value = max_value
        self.default = default
        self.orientation = orientation
        self.max_on_exit = max_on_exit

    @property
    def value(self) -> int:
        return self.widget['value']

    def _prepare_ttk_style(self) -> str:
        style = self.style
        name, ttk_style = style.make_ttk_style(f'.{self.orientation.title()}.TProgressbar')
        kwargs = style.get_map(
            'progress', background='bg',
            troughcolor='trough_color', troughrelief='relief',
            borderwidth='border_width', thickness='bar_width',
        )
        kwargs.setdefault('troughrelief', 'groove')
        ttk_style.configure(name, **kwargs)
        return name

    def pack_into(self, row: Row, column: int):
        horizontal = self.orientation == tkc.HORIZONTAL
        kwargs = {'style': self._prepare_ttk_style(), 'orient': self.orientation, 'value': self.default}
        try:
            width, height = self.size
        except TypeError:
            pass
        else:
            kwargs['length'] = width if horizontal else height

        self.widget = Progressbar(row.frame, mode='determinate', **kwargs)
        self.pack_widget()

    def update(self, value: int, increment: Bool = True, max_value: int = None):
        bar = self.widget
        if max_value is not None:
            self.max_value = max_value
            bar.configure(maximum=max_value)
        if increment:
            bar['value'] += value
        else:
            bar['value'] = value

    def __call__(self, iterable: Iterable[T]) -> Iterator[T]:
        bar = self.widget
        for i, item in enumerate(iterable, bar['value'] + 1):
            yield item
            bar['value'] = i

    def __enter__(self) -> ProgressBar:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.max_on_exit:
            self.widget['value'] = self.max_value
