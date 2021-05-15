"""
Right-Click Menu that supports more advanced callback options than those supported natively by PySimpleGUI.

:author: Doug Skrypa
"""

from functools import partial
from tkinter import Tk, Menu, Event
from typing import Callable, Mapping, Union, Hashable

__all__ = ['ContextualMenu']
MenuDict = Mapping[Hashable, str]


class ContextualMenu:
    def __init__(
        self,
        default_cb: Callable,
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
        self.always_show_default = always_show_default
        self.format_default = format_default
        self.default_key_opt_map = default_key_opt_map
        self.default_cb = default_cb
        self.include_kwargs = include_kwargs
        self.kw_key_option_maps = {}
        self.kw_cb_map = {}
        if kw_key_opt_cb_map:
            for kw, value in kw_key_opt_cb_map.items():
                menu, cb = value if isinstance(value, tuple) else (value, None)
                self.kw_key_option_maps[kw] = menu
                if cb is not None:
                    self.kw_cb_map[kw] = cb

    def _add_options(self, menu: Menu, key_option_map: MenuDict, cb: Callable, do_fmt: bool, kwargs) -> bool:
        added = 0
        for key, option in key_option_map.items():
            command = partial(cb, key, **kwargs) if self.include_kwargs else partial(cb, key)
            menu.add_command(label=option.format(**kwargs) if do_fmt else option, command=command)
            added += 1
        return bool(added)

    def show(self, event: Event, parent: Tk = None, **kwargs) -> bool:
        menu = Menu(parent, tearoff=0)
        added_any = False
        if (self.always_show_default or not kwargs) and self.default_key_opt_map:
            added_defaults = True
            added_any |= self._add_options(menu, self.default_key_opt_map, self.default_cb, self.format_default, kwargs)
        else:
            added_defaults = False

        added_kw_options = False
        for kw_key in kwargs:
            if key_option_map := self.kw_key_option_maps.get(kw_key):
                cb = self.kw_cb_map.get(kw_key, self.default_cb)
                added_kw_options |= self._add_options(menu, key_option_map, cb, True, kwargs)

        added_any |= added_kw_options
        if not added_kw_options and not added_defaults and self.default_key_opt_map:
            added_any |= self._add_options(menu, self.default_key_opt_map, self.default_cb, self.format_default, kwargs)

        if added_any:
            try:
                menu.tk_popup(event.x_root, event.y_root)  # noqa
            finally:
                menu.grab_release()
        return bool(added_any)
