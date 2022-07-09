"""
Table GUI elements

:author: Doug Skrypa
"""

from __future__ import annotations

import logging
import tkinter.constants as tkc
from functools import cached_property
from itertools import chain
from tkinter import Frame, Tcl, Scrollbar
from tkinter.ttk import Treeview, Style as TkStyle
from typing import TYPE_CHECKING, Optional, Callable, Union, Literal
from unicodedata import normalize

from wcwidth import wcswidth

from .element import Element

if TYPE_CHECKING:
    from ..pseudo_elements import Row
    from ..style import Font, Layer

__all__ = ['TableColumn', 'Table']
log = logging.getLogger(__name__)

SelectMode = Literal['none', 'browse', 'extended']
TCL_VERSION = Tcl().eval('info patchlevel')
XGROUND_DEFAULT_HIGHLIGHT_COLOR_MAP = {'foreground': 'SystemHighlightText', 'background': 'SystemHighlight'}


class TableColumn:
    def __init__(self, key: str, title: str = None, width=None, show: bool = True, fmt_str: str = None):
        self.key = key
        self.title = str(title or key)
        self._width = 0
        self.show = show
        self.fmt_str = fmt_str
        self.width = width

    @property
    def width(self):
        return self._width

    @width.setter
    def width(self, value):
        try:
            self._width = max(self._calc_width(value), mono_width(self.title))
        except Exception:
            log.error(f'Error calculating width for column={self.key!r}', exc_info=True)
            raise

    def _calc_width(self, width):
        try:
            return int(width)
        except (TypeError, ValueError):
            pass

        if fmt_str := self.fmt_str:
            def _len(obj):
                return mono_width(fmt_str.format(obj))
        else:
            def _len(obj):
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
                if fmt_str := self.fmt_str:
                    values = []
                    for obj in width:
                        try:
                            values.append(fmt_str.format(obj))
                        except ValueError:
                            values.append(str(obj))
                else:
                    values = list(map(str, width))
                return max(map(mono_width, values))
            raise

    @cached_property
    def format(self) -> Callable:
        return self.fmt_str.format if self.fmt_str else str


class Table(Element):
    widget: Treeview
    frame: Optional[Frame]
    columns: dict[str, TableColumn]

    def __init__(
        self,
        *columns: TableColumn,
        data: list[dict[str, Union[str, int]]],
        rows: int = None,
        show_row_nums: bool = False,
        row_height: int = None,
        alt_row_color: str = None,
        selected_row_color: tuple[str, str] = None,  # fg, bg
        header_text_color: str = None,
        header_bg: str = None,
        header_font: tuple[str, int] = None,
        # row_colors: Sequence[tuple[str, str]] = None,
        select_mode: SelectMode = None,
        scroll_x: bool = False,
        scroll_y: bool = True,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.frame = None
        if show_row_nums:
            columns = chain((TableColumn('#', width=len(f'{len(data):>,d}'), fmt_str='{:>,d}'),), columns)
        self.columns = {col.key: col for col in columns}
        self.data = data
        self.num_rows = rows
        self.show_row_nums = show_row_nums
        self.row_height = row_height
        self.alt_row_color = alt_row_color
        self.selected_row_color = selected_row_color
        self.header_text_color = header_text_color
        self.header_bg = header_bg
        self.header_font = header_font
        # self.row_colors = row_colors
        self.select_mode = select_mode
        self.scroll_x = scroll_x
        self.scroll_y = scroll_y
        self._tree_ids = []

    @classmethod
    def from_data(cls, data: list[dict[str, Union[str, int]]], **kwargs) -> Table:
        keys = {k: None for k in chain.from_iterable(data)}  # dict retains key order, but set does not
        columns = [TableColumn(key, key.replace('_', ' ').title(), data) for key in keys]
        return cls(*columns, data=data, **kwargs)

    def _style(self) -> tuple[str, TkStyle]:
        name = f'{self.id}.customtable.Treeview'
        tk_style = TkStyle()
        style = self.style
        tk_style.theme_use(style.ttk_theme)
        tk_style.configure(name, rowheight=self.row_height or style.char_height('table'))

        # font = style.table.font.default
        # cfg_keys = ('font', 'foreground', 'background', 'fieldbackground')
        # bg = style.table.bg.default
        # if base := {k: v for k, v in zip(cfg_keys, (font, style.fg.default, bg, bg)) if v is not None}:
        #     tk_style.configure(name, **base)

        if base := self._tk_style_config(tk_style, name, 'table'):
            if (selected_row_color := self.selected_row_color) and ('foreground' in base or 'background' in base):
                for i, (xground, default) in enumerate(XGROUND_DEFAULT_HIGHLIGHT_COLOR_MAP.items()):
                    if xground in base and (selected := selected_row_color[i]) is not None:
                        tk_style.map(name, **{xground: _style_map_data(tk_style, name, xground, selected or default)})

                # for i, color in enumerate(('foreground', 'background')):
                #     if color in base and selected_row_color[i] is not None:
                #         tk_style.map(name, **{color: _fixed_style_map(tk_style, name, color, selected_row_color)})

        self._tk_style_config(tk_style, f'{name}.Heading', 'table_header')
        # header_vals = (self.header_font or font, self.header_text_color, self.header_bg)
        # if header_kwargs := {k: v for k, v in zip(cfg_keys, header_vals) if v is not None}:
        #     tk_style.configure(f'{name}.Heading', **header_kwargs)

        return name, tk_style

    def _tk_style_config(self, tk_style: TkStyle, name: str, layer: Layer) -> dict[str, Union[Font, str, None]]:
        config = self.style.get('font', layer=layer, fg='foreground', bg='background')  # noqa
        config = {k: v for k, v in config.items() if v is not None}
        if layer == 'table' and (bg := config.get('background')):
            config['fieldbackground'] = bg
        tk_style.configure(name, **config)
        return config

    def pack_into(self, row: Row):
        self.frame = frame = Frame(row.frame)
        columns = self.columns
        height = self.num_rows if self.num_rows else self.size[1] if self.size else len(self.data)
        log.debug(f'Creating Table Treeview with {height=}')
        self.widget = tree_view = Treeview(
            frame,
            columns=[col.key for col in columns.values()],
            displaycolumns=[col.key for col in columns.values() if col.show],
            height=height,
            show='headings',
            selectmode=self.select_mode,
        )
        log.debug(f'Getting char_width from {self.style=}')
        char_width = self.style.char_width('table')
        log.debug(f'Processing columns; {char_width=}')
        for column in columns.values():
            tree_view.heading(column.key, text=column.title)
            width = column.width * char_width + 10
            log.debug(f'  Adding column with key={column.key!r} title={column.title!r} {width=}')
            # tree_view.column(column.key, width=width, minwidth=10, anchor=self.anchor, stretch=0)
            tree_view.column(column.key, width=width, minwidth=10, stretch=False)

        for i, row in enumerate(self.data):
            values = (val for key, val in row.items() if columns[key].show)
            values = [i, *values] if self.show_row_nums else list(values)
            # self._tree_ids.append(tree_view.insert('', 'end', text=values, iid=i + 1, values=values, tag=i))
            self._tree_ids.append(tree_view.insert('', 'end', text=values, iid=i, values=values, tag=i))

        if alt_color := self.alt_row_color:
            for row in range(0, len(self.data), 2):
                tree_view.tag_configure(row, background=alt_color)

        tree_view.configure(style=self._style()[0])
        # tree_view.bind('<<TreeviewSelect>>', self._treeview_selected)
        if self.scroll_y:
            scroll_bar_y = Scrollbar(frame)
            scroll_bar_y.pack(side=tkc.RIGHT, fill='y')
            scroll_bar_y.configure(command=tree_view.yview)
            tree_view.configure(yscrollcommand=scroll_bar_y.set)
        if self.scroll_x:
            scroll_bar_x = Scrollbar(frame, orient=tkc.HORIZONTAL)
            scroll_bar_x.pack(side=tkc.BOTTOM, fill='x')
            scroll_bar_x.configure(command=tree_view.xview)
            tree_view.configure(xscrollcommand=scroll_bar_x.set)

        # tree_view.pack(side=tkc.LEFT, expand=True, padx=0, pady=0, fill='both')
        self.pack_widget(expand=True, fill='both', padx=0, pady=0)
        # frame.pack(side=tkc.LEFT, expand=True, **self.pad_kw)
        frame.pack(anchor=self.anchor.value, side=self.side.value, expand=True, **self.pad_kw)


def _style_map_data(style: TkStyle, name: str, query_opt: str, selected_color: str = None):
    # Based on the fix for setting text color for Tkinter 8.6.9 from: https://core.tcl.tk/tk/info/509cafafae
    base = [ele for ele in style.map('Treeview', query_opt=query_opt) if '!' not in ele[0]]
    rows = [ele for ele in style.map(name, query_opt=query_opt) if '!' not in ele[0]]
    if selected_color:
        rows.append(('selected', selected_color))
    return rows + base


# def _fixed_style_map(style: TkStyle, style_name: str, option: str, highlight_colors: tuple[str, str] = (None, None)):
#     # Fix for setting text color for Tkinter 8.6.9
#     # From: https://core.tcl.tk/tk/info/509cafafae
#     default_map = [elm for elm in style.map('Treeview', query_opt=option) if '!' not in elm[0]]
#     custom_map = [elm for elm in style.map(style_name, query_opt=option) if '!' not in elm[0]]
#
#     if option == 'background':
#         custom_map.append(('selected', highlight_colors[1] or 'SystemHighlight'))
#     elif option == 'foreground':
#         custom_map.append(('selected', highlight_colors[0] or 'SystemHighlightText'))
#
#     return custom_map + default_map


def mono_width(text: str) -> int:
    return wcswidth(normalize('NFC', text))
