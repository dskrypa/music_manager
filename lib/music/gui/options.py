"""
Gui option rendering and parsing

:author: Doug Skrypa
"""

import logging
from typing import TYPE_CHECKING, Any, Callable, Optional

from PySimpleGUI import Text, Element, Checkbox, Frame, Submit, Input

if TYPE_CHECKING:
    from .views.base import GuiView

__all__ = ['GuiOptions', 'GuiOptionError', 'SingleParsingError', 'RequiredOptionMissing', 'MultiParsingError']
log = logging.getLogger(__name__)
_NotSet = object()


class GuiOptions:
    def __init__(self, view: 'GuiView', *, submit: Optional[str] = 'Submit', disable_on_parsed: bool = False):
        self.view = view
        self.options = {}
        self.parsed = False
        self.disable_on_parsed = disable_on_parsed
        self.submit_text = submit

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

    def _add_option(
        self,
        opt_type: str,
        option: str,
        label: str,
        default: Any = _NotSet,
        disabled: bool = False,
        row: int = 0,
        required: bool = False,
        **kwargs
    ):
        self.options[option] = {
            'name': option,
            'label': label,
            'default': default,
            'disabled': disabled,
            'opt_type': opt_type,
            'row': row,
            'required': required,
            **kwargs
        }

    def add_bool(self, option: str, label: str, default: bool = False, *, tooltip: str = None, **kwargs):
        self._add_option('checkbox', option, label, default, tooltip=tooltip, **kwargs)

    # noinspection PyShadowingBuiltins
    def add_input(self, option: str, label: str, default: Any = _NotSet, *, type: Callable = str, **kwargs):
        self._add_option('input', option, label, default, type=type, **kwargs)

    def layout(self, submit_key: str, disable_all: bool = None, submit_row: int = None) -> list[list[Element]]:
        if disable_all is None:
            disable_all = self.disable_on_parsed and self.parsed
        log.debug(f'Building option layout for view={self.view} with {self.parsed=!r} {submit_key=!r} {disable_all=!r}')

        layout = []
        for name, opt in self.options.items():
            row_num, opt_type = opt['row'], opt['opt_type']
            while len(layout) < (row_num + 1):
                layout.append([])
            row = layout[row_num]  # type: list[Element]

            val = opt.get('value', opt['default'])
            common = {'key': f'opt::{name}', 'disabled': disable_all or opt['disabled']}
            if opt_kwargs := opt.get('kwargs'):
                common.update(opt_kwargs)

            if opt_type == 'checkbox':
                row.append(Checkbox(opt['label'], default=val, tooltip=opt['tooltip'], **common))
            elif opt_type == 'input':
                row.append(Text(opt['label'], key=f'lbl::{name}'))
                row.append(Input('' if val is _NotSet else val, **common))
            else:
                raise ValueError(f'Unsupported {opt_type=!r}')

        if self.submit_text:
            submit_ele = Submit(self.submit_text, disabled=disable_all, key=submit_key)
            if submit_row is None:
                layout.append([submit_ele])
            else:
                while len(layout) < (submit_row + 1):
                    layout.append([])
                layout[submit_row].append(submit_ele)

        return layout

    def as_frame(self, *args, **kwargs) -> Frame:
        return Frame('options', self.layout(*args, **kwargs))

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
