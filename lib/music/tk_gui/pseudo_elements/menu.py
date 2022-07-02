"""
Right-Click Menu that supports more advanced callback options than those supported natively by PySimpleGUI.

:author: Doug Skrypa
"""

import webbrowser
from dataclasses import dataclass
from enum import Enum
from functools import partial
from tkinter import Tk, Menu, Event
from typing import Callable, Mapping, Union, Hashable
from urllib.parse import quote_plus

__all__ = ['ContextualMenu', 'ShowMode', 'SearchMenu']

CallbackArg = Hashable
MenuDict = Mapping[CallbackArg, str]


class ShowMode(Enum):
    NEVER = 'never'
    ALWAYS = 'always'
    ON_KEYWORD = 'keyword'
    ON_KW_VALUE_TRUTHY = 'kw_value_truthy'
    ON_NO_KWARGS = 'no_kwargs'
    ON_CB_ARG_TRUTHY = 'cb_arg'


class ContextualMenu:
    __slots__ = ('default_cb', '_options')

    def __init__(
        self,
        default_cb: Callable = None,
        default_key_opt_map: MenuDict = None,
        kw_key_opt_cb_map: Mapping[str, Union[tuple[MenuDict, Callable], MenuDict]] = None,
        always_show_default: bool = True,
        format_default: bool = True,
        include_kwargs: bool = True,
    ):
        """
        A right-click menu that can provide different options based on values passed at run time.

        :param default_cb: Default callback for the default options and when a keyword-based option does not have its
          own callback
        :param default_key_opt_map: Mapping of {callback arg: option string} to include by default
        :param kw_key_opt_cb_map: Mapping of {keyword: ({callback arg: option formatting string}, callback)} or
          {keyword: {callback arg: option formatting string}} for keywords
        :param always_show_default: Always show default options, even when kwargs are passed to :meth:`.show`
        :param format_default: Treat default options as formatting strings to format kwargs like the kwarg-based options
        :param include_kwargs: Include kwargs when calling the callback
        """
        self.default_cb = default_cb
        self._options: list[MenuOption] = []
        if default_key_opt_map:
            show = ShowMode.ALWAYS if always_show_default else ShowMode.ON_NO_KWARGS
            for cb_arg, option in default_key_opt_map.items():
                self.add_option(option, cb_arg, show=show, format=format_default, call_with_kwargs=include_kwargs)
        if kw_key_opt_cb_map:
            for kw, value in kw_key_opt_cb_map.items():
                key_opt_map, cb = value if isinstance(value, tuple) else (value, None)
                for cb_arg, option in key_opt_map.items():
                    self.add_option(option, cb_arg, cb, kw, ShowMode.ON_KEYWORD, call_with_kwargs=include_kwargs)

    def add_option(
        self,
        text: str,
        cb_arg: CallbackArg,
        cb: Callable = None,
        keyword: str = None,
        show: Union[ShowMode, str] = None,
        format: bool = True,  # noqa
        call_with_kwargs: bool = True,
    ):
        if (cb := cb or self.default_cb) is None:
            raise TypeError(f'A callback is required for option {text=}')
        show = (ShowMode.ON_KEYWORD if keyword else ShowMode.ALWAYS) if show is None else ShowMode(show)
        self._options.append(MenuOption(text, cb_arg, show, format, keyword, cb, call_with_kwargs))

    def show(self, event: Event, parent: Tk = None, **kwargs) -> bool:
        menu = Menu(parent, tearoff=0)
        added_any = False
        for option in self._options:
            added_any |= option.maybe_add(menu, kwargs)

        if added_any:
            try:
                menu.tk_popup(event.x_root, event.y_root)  # noqa
            finally:
                menu.grab_release()
        return added_any


@dataclass
class MenuOption:
    text: str
    cb_arg: CallbackArg
    show: ShowMode
    format: bool = True
    keyword: str = None
    callback: Callable = None
    call_with_kwargs: bool = True

    def maybe_add(self, menu: Menu, kwargs: dict) -> bool:
        if not self.should_show(kwargs):
            return False
        menu.add_command(label=self.format_text(kwargs), command=self.prepare_cb(kwargs))
        return True

    def should_show(self, kwargs: dict) -> bool:
        show = self.show
        if show == ShowMode.NEVER:
            return False
        elif show == ShowMode.ALWAYS:
            return True
        elif show == ShowMode.ON_KEYWORD:
            return self.keyword in kwargs
        elif show == ShowMode.ON_KW_VALUE_TRUTHY:
            return bool(kwargs.get(self.keyword))
        elif show == ShowMode.ON_NO_KWARGS:
            return not kwargs
        elif show == ShowMode.ON_CB_ARG_TRUTHY:
            return bool(self.cb_arg)
        else:
            return False

    def format_text(self, kwargs: dict) -> str:
        return self.text.format(**kwargs) if self.format else self.text

    def prepare_cb(self, kwargs: dict):
        if self.call_with_kwargs:
            return partial(self.callback, self.cb_arg, **kwargs)
        return partial(self.callback, self.cb_arg)


class SearchMenu(ContextualMenu):
    search_menu_options = {
        'google': 'Search Google for {selected!r}',
        'kpop.fandom': 'Search kpop.fandom.com for {selected!r}',
        'generasia': 'Search generasia for {selected!r}',
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for cb_arg, option in self.search_menu_options.items():
            self.add_option(option, cb_arg, self._search_for_selection, 'selected', 'kw_value_truthy')

    @staticmethod
    def _search_for_selection(key: str, selected: str):
        quoted = quote_plus(selected)
        if key == 'kpop.fandom':
            webbrowser.open(f'https://kpop.fandom.com/wiki/Special:Search?scope=internal&query={quoted}')
        elif key == 'google':
            webbrowser.open(f'https://www.google.com/search?q={quoted}')
        elif key == 'generasia':
            url = f'https://www.generasia.com/w/index.php?title=Special%3ASearch&fulltext=Search&search={quoted}'
            webbrowser.open(url)
