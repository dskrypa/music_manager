"""
Unification of CLI and GUI prompts

:author: Doug Skrypa
"""

import logging
from enum import Enum
from getpass import getpass as cli_getpass
from typing import Union, Callable, Collection, Any, Optional

from ds_tools.input.prompts import choose_item as cli_choose_item, Color, get_input as cli_get_input, _NotSet
from ds_tools.input.parsers import parse_yes_no

from tk_gui.popups import popup_yes_no as tkg_yes_no, popup_get_text as tkg_get_text, popup_get_password as tkg_get_pw
from tk_gui.popups import choose_item as tkg_choose_item

from ..gui.popups.choose_item import choose_item as gui_choose_item
from ..gui.popups.simple import popup_yes_no
from ..gui.popups.text import popup_get_text

__all__ = ['choose_item', 'UIMode', 'set_ui_mode', 'get_input', 'getpass']
log = logging.getLogger(__name__)


class UIMode(Enum):
    CLI = 'cli'
    GUI = 'gui'
    TK_GUI = 'tk_gui'

    @classmethod
    def current(cls):
        return UI_MODE


UI_MODE = UIMode.CLI


def set_ui_mode(mode: Union[str, UIMode]):
    global UI_MODE
    UI_MODE = UIMode(mode)


def choose_item(
    items: Collection[Any],
    name: str = 'value',
    source: Any = '',
    *,
    before: Optional[str] = None,
    retry: int = 0,
    before_color: Color = None,
    prompt_color: Color = 14,
    error_color: Color = 9,
    repr_func: Callable = repr,
):
    log.debug(f'choose_item with {UI_MODE=}: {list(items)}')
    if UI_MODE == UIMode.CLI:
        return cli_choose_item(
            items,
            name,
            source,
            before=before,
            retry=retry,
            before_color=before_color,
            prompt_color=prompt_color,
            error_color=error_color,
            repr_func=repr_func,
        )
    elif UI_MODE == UIMode.TK_GUI:
        return tkg_choose_item(items, item_name=name, source=source, text=before, repr_func=repr_func, keep_on_top=True)
    else:
        return gui_choose_item(items, name, source, before=before, repr_func=repr_func)


def get_input(
    prompt: str,
    skip: bool = False,
    retry: int = 0,
    parser: Callable = parse_yes_no,
    *,
    default=_NotSet,
    input_func: Callable = input,
    **kwargs,
):
    if UI_MODE == UIMode.CLI:
        return cli_get_input(prompt, skip, retry, parser, default=default, input_func=input_func)
    elif skip and default is _NotSet:
        raise ValueError(f'Unable to skip user prompt without a default value: {prompt!r}')
    elif parser is parse_yes_no:
        if UI_MODE == UIMode.TK_GUI:
            return tkg_yes_no(prompt, keep_on_top=True, **kwargs)
        return popup_yes_no(prompt, **kwargs)
    else:
        if UI_MODE == UIMode.TK_GUI:
            result = tkg_get_text(prompt, keep_on_top=True, **kwargs)
        else:
            result = popup_get_text(prompt, **kwargs)
        return parser(result)


def getpass(prompt: str, **kwargs):
    if UI_MODE == UIMode.CLI:
        return cli_getpass(prompt)
    elif UI_MODE == UIMode.TK_GUI:
        return tkg_get_pw(prompt, keep_on_top=True, **kwargs)
    else:
        return popup_get_text(prompt, password_char='*', **kwargs)
