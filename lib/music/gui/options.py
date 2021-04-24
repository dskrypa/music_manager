"""
Gui option rendering and parsing

:author: Doug Skrypa
"""

from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Callable, Optional, Collection, Iterator, Mapping

from PySimpleGUI import Text, Element, Checkbox, Frame, Submit, Column, Combo, Listbox

from .views.utils import resize_text_column, make_checkbox_grid, DarkInput as Input

if TYPE_CHECKING:
    from .views.base import GuiView

__all__ = ['GuiOptions', 'GuiOptionError', 'SingleParsingError', 'RequiredOptionMissing', 'MultiParsingError']
_NotSet = object()
COMMON_PARAMS = ('size', 'tooltip', 'pad', 'enable_events')


class GuiOptions:
    def __init__(
        self,
        view: 'GuiView',
        *,
        submit: Optional[str] = 'Submit',
        disable_on_parsed: bool = False,
        align_text: bool = True,
        align_checkboxes: bool = True,
    ):
        self.view = view
        self.options = {}
        self.parsed = False
        self.disable_on_parsed = disable_on_parsed
        self.submit_text = submit
        self.align_text = align_text
        self.align_checkboxes = align_checkboxes
        self._rows_per_column = {}
        self._default_row = 0
        self._default_col = 0

    @property
    def log(self):
        return self.view.log

    def __getitem__(self, name: str):
        try:
            option = self.options[name]
        except KeyError:
            raise NoSuchOptionError(f'Invalid option={name!r}') from None
        try:
            return option['value']
        except KeyError:
            default = option['default']
            if default is not _NotSet:
                return default
            raise

    def __setitem__(self, name: str, value: Any):
        try:
            option = self.options[name]
        except KeyError:
            raise NoSuchOptionError(f'Invalid option={name!r}') from None
        option['value'] = value

    def get(self, name: str, default=_NotSet):
        try:
            return self[name]
        except KeyError:
            if default is _NotSet:
                raise KeyError(f'No value or default has been provided for option={name!r}') from None
            return default

    def update(self, options: Optional[Mapping[str, Any]]):
        """Update the selected options based on previous input"""
        if options is None:
            return
        for key, val in options.items():
            try:
                self[key] = val
            except NoSuchOptionError:
                pass

    def items(self) -> Iterator[tuple[str, Any]]:
        for name in self.options:
            try:
                yield name, self[name]
            except KeyError:
                pass

    def _add_option(
        self,
        opt_type: str,
        option: str,
        label: str,
        default: Any = _NotSet,
        disabled: bool = False,
        row: int = _NotSet,
        col: Optional[int] = _NotSet,
        required: bool = False,
        **kwargs
    ):
        row = self._default_row if row is _NotSet else row
        col = self._default_col if col is _NotSet else col
        self.options[option] = {
            'name': option,
            'label': label,
            'default': default,
            'disabled': disabled,
            'opt_type': opt_type,
            'row': row,
            'col': col,
            'required': required,
            **kwargs
        }
        col_rows = self._rows_per_column.get(col, 0)
        self._rows_per_column[col] = max(col_rows, row + 1)

    def add_bool(self, option: str, label: str, default: bool = False, **kwargs):
        self._add_option('checkbox', option, label, default, **kwargs)

    # noinspection PyShadowingBuiltins
    def add_input(self, option: str, label: str, default: Any = _NotSet, *, type: Callable = str, **kwargs):
        self._add_option('input', option, label, default, type=type, **kwargs)

    def add_dropdown(self, option: str, label: str, choices: Collection[str], default: Any = None, **kwargs):
        self._add_option('dropdown', option, label, default, choices=choices, **kwargs)

    def add_listbox(
        self,
        option: str,
        label: str,
        choices: Collection[str],
        default: Any = _NotSet,
        *,
        size: tuple[int, int] = None,
        select_mode: str = 'extended',
        **kwargs
    ):
        kwargs.update(size=size or (max(map(len, choices)) + 3, len(choices)), select_mode=select_mode, choices=choices)
        self._add_option('listbox', option, label, choices if default is _NotSet else default, **kwargs)

    def _generate_layout(self, disable_all: bool) -> Iterator[tuple[Optional[int], int, Element]]:
        for name, opt in self.options.items():
            opt_type, col_num, row_num = opt['opt_type'], opt['col'], opt['row']
            val = opt.get('value', opt['default'])
            common = {'key': f'opt::{name}', 'disabled': disable_all or opt['disabled']}
            if opt_kwargs := opt.get('kwargs'):
                common.update(opt_kwargs)
            for param in COMMON_PARAMS:
                try:
                    common[param] = opt[param]
                except KeyError:
                    pass

            if opt_type == 'checkbox':
                yield col_num, row_num, Checkbox(opt['label'], default=val, **common)
            elif opt_type == 'input':
                yield col_num, row_num, Text(opt['label'], key=f'lbl::{name}')
                yield col_num, row_num, Input('' if val is _NotSet else val, **common)
            elif opt_type == 'dropdown':
                yield col_num, row_num, Text(opt['label'], key=f'lbl::{name}')
                yield col_num, row_num, Combo(opt['choices'], default_value=val, **common)
            elif opt_type == 'listbox':
                choices = opt['choices']
                yield col_num, row_num, Text(opt['label'], key=f'lbl::{name}')
                yield col_num, row_num, Listbox(
                    choices, default_values=val or choices, no_scrollbar=True, select_mode=opt['select_mode'], **common
                )
            else:
                raise ValueError(f'Unsupported {opt_type=!r}')

    def _pack(self, layout: list[list[Element]], columns: list[list[list[Element]]]) -> list[list[Element]]:
        if self.align_text or self.align_checkboxes:
            if columns:
                row_sets = [layout + columns[0], columns[1:]] if len(columns) > 1 else [layout + columns[0]]
            else:
                row_sets = [layout]

            for row_set in row_sets:
                if self.align_text and (rows_with_text := [r for r in row_set if r and isinstance(r[0], Text)]):
                    resize_text_column(rows_with_text)  # noqa
                if self.align_checkboxes:
                    if box_rows := [r for r in row_set if r and all(isinstance(e, Checkbox) for e in r)]:
                        self.log.info(f'Processing checkboxes into grid: {box_rows}')
                        make_checkbox_grid(box_rows)  # noqa

        if not layout and len(columns) == 1:
            layout = columns[0]
        else:
            column_objects = [
                Column(column, key=f'col::options::{i}', pad=(0, 0), expand_x=True) for i, column in enumerate(columns)
            ]
            layout.append(column_objects)

        return layout

    def layout(self, submit_key: str, disable_all: bool = None, submit_row: int = None) -> list[list[Element]]:
        if disable_all is None:
            disable_all = self.disable_on_parsed and self.parsed
        self.log.debug(f'Building option layout with {self.parsed=!r} {submit_key=!r} {disable_all=!r}')

        rows_per_column = sorted(((col, val) for col, val in self._rows_per_column.items() if col is not None))
        layout = [[] for _ in range(none_cols)] if (none_cols := self._rows_per_column.get(None)) else []
        columns = [[[] for _ in range(r)] for c, r in rows_per_column]
        for col_num, row_num, ele in self._generate_layout(disable_all):
            if col_num is None:
                layout[row_num].append(ele)
            else:
                columns[col_num][row_num].append(ele)

        layout = self._pack(layout, columns)

        if self.submit_text:
            submit_ele = Submit(self.submit_text, disabled=disable_all, key=submit_key)
            if submit_row is None:
                layout.append([submit_ele])
            else:
                while len(layout) < (submit_row + 1):
                    layout.append([])
                layout[submit_row].append(submit_ele)

        return layout

    def as_frame(self, *args, **kwargs) -> Column:
        frame = Frame('options', self.layout(*args, **kwargs), key='frame::options')
        return Column([[frame]], key='col::frame_options', justification='center')

    def parse(self, data: dict[str, Any]) -> dict[str, Any]:
        errors = []
        parsed = {}
        defaults = []
        for name, opt in self.options.items():
            try:
                val = data[f'opt::{name}']
            except KeyError:
                if opt['required']:
                    errors.append(RequiredOptionMissing(opt))
                elif opt['default'] is _NotSet:
                    pass
                else:
                    defaults.append(name)
            else:
                if isinstance(val, str):
                    val = val.strip()

                opt_type = opt['opt_type']
                if opt_type == 'input' and opt['type'] is not str:
                    try:
                        val = opt['type'](val)
                    except Exception as e:
                        errors.append(SingleParsingError(opt, f'Error parsing {val=!r} for option={name!r}: {e}', val))
                    else:
                        parsed[name] = val
                else:
                    parsed[name] = val

        for name, val in parsed.items():
            self.options[name]['value'] = parsed[name]  # Save the value even if an exception will be raised

        self.parsed = True
        if errors:
            raise errors[0] if len(errors) == 1 else MultiParsingError(errors)

        for name in defaults:
            parsed[name] = self.options[name]['default']

        return parsed

    @contextmanager
    def column(self, col: Optional[int]):
        old = self._default_col
        self._default_col = col
        try:
            yield self
        finally:
            self._default_col = old

    @contextmanager
    def row(self, row: int):
        old = self._default_row
        self._default_row = row
        try:
            yield self
        finally:
            self._default_row = old

    @contextmanager
    def column_and_row(self, col: Optional[int], row: int):
        old_col, old_row = self._default_col, self._default_row
        self._default_col = col
        self._default_row = row
        try:
            yield self
        finally:
            self._default_col = old_col
            self._default_row = old_row


class GuiOptionError(Exception):
    """Base exception for parsing exceptions"""


class NoSuchOptionError(GuiOptionError):
    """Exception to be raised when attempting to access/set an option that does not exist"""


class SingleParsingError(GuiOptionError):
    def __init__(self, option: dict[str, Any], message: str = None, value: Any = None):
        self.option = option
        self.message = message
        self.value = value

    def __str__(self):
        return self.message


class RequiredOptionMissing(SingleParsingError):
    def __str__(self):
        return f'Missing value for required option={self.option["name"]}'


class MultiParsingError(GuiOptionError):
    def __init__(self, errors: list[SingleParsingError]):
        self.errors = errors

    def __str__(self):
        return '\n'.join(map(str, self.errors))
