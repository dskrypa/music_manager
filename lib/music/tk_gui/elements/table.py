"""
Table GUI elements

:author: Doug Skrypa
"""

from __future__ import annotations

import logging
from itertools import chain
from tkinter.ttk import Treeview, Style as TtkStyle
from typing import TYPE_CHECKING, Union, Callable, Literal, Mapping, Any, Iterable
from unicodedata import normalize

from wcwidth import wcswidth

from ..pseudo_elements.scroll import ScrollableTreeview
from .element import Element

if TYPE_CHECKING:
    from ..pseudo_elements import Row
    from ..style import Font, Layer

__all__ = ['TableColumn', 'Table']
log = logging.getLogger(__name__)

SelectMode = Literal['none', 'browse', 'extended']
XGROUND_DEFAULT_HIGHLIGHT_COLOR_MAP = {'foreground': 'SystemHighlightText', 'background': 'SystemHighlight'}
_Width = Union[float, Mapping[Any, Mapping[str, Any]], Iterable[Union[Mapping[str, Any], Any]]]
FormatFunc = Callable[[Any], str]


class TableColumn:
    __slots__ = ('key', 'title', '_width', 'show', 'fmt_func')

    def __init__(
        self, key: str, title: str = None, width: _Width = None, show: bool = True, fmt_func: FormatFunc = None
    ):
        self.key = key
        self.title = str(title or key)
        self._width = 0
        self.show = show
        self.fmt_func = fmt_func
        self.width = width

    @property
    def width(self) -> int:
        return self._width

    @width.setter
    def width(self, value: _Width):
        try:
            self._width = max(self._calc_width(value), mono_width(self.title))
        except Exception:
            log.error(f'Error calculating width for column={self.key!r}', exc_info=True)
            raise

    def _calc_width(self, width: _Width) -> int:
        try:
            return int(width)
        except (TypeError, ValueError):
            pass

        if fmt_func := self.fmt_func:
            def _len(obj: Any):
                return mono_width(fmt_func(obj))
        else:
            def _len(obj: Any):
                return mono_width(str(obj))

        key = self.key
        try:
            return max(_len(e[key]) for e in width.values())
        except (KeyError, TypeError, AttributeError):
            pass
        try:
            return max(_len(e[key]) for e in width)
        except (KeyError, TypeError, AttributeError):
            pass
        try:
            return max(map(_len, width))
        except ValueError as e:
            if 'Unknown format code' in str(e):
                if fmt_func := self.fmt_func:
                    values = []
                    for obj in width:
                        try:
                            values.append(fmt_func(obj))
                        except ValueError:
                            values.append(str(obj))
                else:
                    values = list(map(str, width))
                return max(map(mono_width, values))
            raise


class Table(Element):
    widget: Union[Treeview, ScrollableTreeview]
    columns: dict[str, TableColumn]

    def __init__(
        self,
        *columns: TableColumn,
        data: list[dict[str, Union[str, int]]],
        rows: int = None,
        show_row_nums: bool = False,
        row_height: int = None,
        selected_row_color: tuple[str, str] = None,  # fg, bg
        select_mode: SelectMode = None,
        scroll_y: bool = True,
        scroll_x: bool = False,
        **kwargs,
    ):
        super().__init__(**kwargs)
        if show_row_nums:
            columns = chain((TableColumn('#', width=len(f'{len(data):>,d}'), fmt_func='{:>,d}'.format),), columns)
        self.columns = {col.key: col for col in columns}
        self.data = data
        self.num_rows = rows
        self.show_row_nums = show_row_nums
        self.row_height = row_height
        self.selected_row_color = selected_row_color
        self.select_mode = select_mode
        self.scroll_x = scroll_x
        self.scroll_y = scroll_y
        self._tree_ids = []

    @classmethod
    def from_data(cls, data: list[dict[str, Union[str, int]]], **kwargs) -> Table:
        keys = {k: None for k in chain.from_iterable(data)}  # dict retains key order, but set does not
        columns = [TableColumn(key, key.replace('_', ' ').title(), data) for key in keys]
        return cls(*columns, data=data, **kwargs)

    def _ttk_style(self) -> tuple[str, TtkStyle]:
        style = self.style
        name, ttk_style = style.make_ttk_style('customtable.Treeview')
        ttk_style.configure(name, rowheight=self.row_height or style.char_height('table'))

        if base := self._tk_style_config(ttk_style, name, 'table'):
            if (selected_row_color := self.selected_row_color) and ('foreground' in base or 'background' in base):
                for i, (xground, default) in enumerate(XGROUND_DEFAULT_HIGHLIGHT_COLOR_MAP.items()):
                    if xground in base and (selected := selected_row_color[i]) is not None:
                        ttk_style.map(name, **{xground: _style_map_data(ttk_style, name, xground, selected or default)})

        self._tk_style_config(ttk_style, f'{name}.Heading', 'table_header')
        return name, ttk_style

    def _tk_style_config(self, ttk_style: TtkStyle, name: str, layer: Layer) -> dict[str, Union[Font, str, None]]:
        config = self.style.get_map(layer, foreground='fg', background='bg', font='font')
        if layer == 'table' and (bg := config.get('background')):
            config['fieldbackground'] = bg
        ttk_style.configure(name, **config)
        return config

    def pack_into(self, row: Row, column: int):
        columns, style = self.columns, self.style
        kwargs = {
            'columns': [col.key for col in columns.values()],
            'displaycolumns': [col.key for col in columns.values() if col.show],
            'height': self.num_rows if self.num_rows else self.size[1] if self.size else len(self.data),
            'show': 'headings',
            'selectmode': self.select_mode,
            **self.style_config,
        }
        if self.scroll_y or self.scroll_x:
            self.widget = outer = ScrollableTreeview(row.frame, self.scroll_y, self.scroll_x, style, **kwargs)
            tree_view = outer.inner_widget
        else:
            self.widget = tree_view = Treeview(row.frame, **kwargs)

        char_width = style.char_width('table')
        for column in columns.values():
            tree_view.heading(column.key, text=column.title)
            tree_view.column(column.key, width=column.width * char_width + 10, minwidth=10, stretch=False)

        for i, row in enumerate(self.data):
            values = (val for key, val in row.items() if columns[key].show)
            values = [i, *values] if self.show_row_nums else list(values)
            self._tree_ids.append(tree_view.insert('', 'end', text=values, iid=i, values=values, tag=i))  # noqa

        if alt_row_style := style.table_alt:
            font, fg, bg = alt_row_style.font.default, alt_row_style.fg.default, alt_row_style.bg.default
            for row in range(0, len(self.data), 2):
                tree_view.tag_configure(row, background=bg, foreground=fg, font=font)  # noqa

        tree_view.configure(style=self._ttk_style()[0])
        # tree_view.bind('<<TreeviewSelect>>', self._treeview_selected)
        self.pack_widget(expand=True)


def _style_map_data(style: TtkStyle, name: str, query_opt: str, selected_color: str = None):
    # Based on the fix for setting text color for Tkinter 8.6.9 from: https://core.tcl.tk/tk/info/509cafafae
    base = _filtered_style_map_eles(style, 'Treeview', query_opt)
    rows = _filtered_style_map_eles(style, name, query_opt)
    if selected_color:
        rows.append(('selected', selected_color))
    return rows + base


def _filtered_style_map_eles(style: TtkStyle, name: str, query_opt: str):
    return [ele for ele in style.map(name, query_opt=query_opt) if '!' not in ele[0] and 'selected' not in ele[0]]


def mono_width(text: str) -> int:
    return wcswidth(normalize('NFC', text))
