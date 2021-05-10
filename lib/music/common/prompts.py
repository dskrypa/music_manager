"""
Unification of CLI and GUI prompts

:author: Doug Skrypa
"""

from enum import Enum
from typing import Union, Callable, Collection, Any, Optional

from ds_tools.input.prompts import choose_item as cli_choose_item, Color
from ..gui.popups.choose_item import choose_item as gui_choose_item

__all__ = ['choose_item', 'UIMode', 'set_ui_mode']


class UIMode(Enum):
    CLI = 'cli'
    GUI = 'gui'


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
    else:
        return gui_choose_item(items, name, source, before=before, repr_func=repr_func)
