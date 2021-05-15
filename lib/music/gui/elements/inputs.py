"""
Input elements for PySimpleGUI

:author: Doug Skrypa
"""

import webbrowser
from functools import partial
from pathlib import Path
from tkinter import TclError, Entry
from typing import Union, Optional

from PySimpleGUI import Input, theme, theme_input_background_color, theme_input_text_color

from ..utils import open_in_file_manager
from .menu import ContextualMenu

__all__ = ['ExtInput']
MenuListItem = Union[str, list[Union[str, 'MenuListItem']]]
MenuList = list[MenuListItem]


class ExtInput(Input):
    TKEntry: Entry

    def __init__(
        self,
        value='',
        *args,
        right_click_menu: Union[ContextualMenu, MenuList] = None,
        link: bool = None,
        tooltip: str = None,
        path: Union[bool, str, Path] = None,
        **kwargs,
    ):
        """
        :param value: The initial value to display
        :param args: Positional arguments to pass to :class:`PySimpleGUI.Input`
        :param right_click_menu: Either a vanilla right-click menu as a list of strings/lists supported by PySimpleGUI
          or a :class:`ContextualMenu`
        :param link: Whether the displayed text should be hyperlinked to open a browser with the text as the URL
          (default: link if the text starts with ``http://`` or ``https://``)
        :param tooltip: A tooltip to be displayed when hovering over this element.  If link / a link is detected, then
          additional information will be appended to this value.
        :param path: To allow right-click to open a path in file manager, set to True to use the displayed text, or
          specify a specific path to open
        :param kwargs: Keyword arguments to pass to :class:`PySimpleGUI.Input`
        """
        self._dark = 'dark' in theme().lower()
        if self._dark:
            kwargs.setdefault('background_color', theme_input_background_color())
            kwargs.setdefault('text_color', theme_input_text_color())
            kwargs.setdefault('disabled_readonly_background_color', '#a2a2a2')
            kwargs.setdefault('disabled_readonly_text_color', '#000000')
        if link or (link is None and str(value).startswith(('http://', 'https://'))):
            if tooltip:
                tooltip = f'{tooltip}; open link in browser with ctrl + click'
            else:
                tooltip = 'Open link in browser with ctrl + click'
        super().__init__(value, *args, tooltip=tooltip, **kwargs)
        self._valid_value = True
        self._link = link or link is None
        self._path = path
        self.right_click_menu = right_click_menu

    @property
    def right_click_menu(self) -> Optional[ContextualMenu]:
        return self._right_click_menu

    @right_click_menu.setter
    def right_click_menu(self, menu: Union[ContextualMenu, MenuList, None]):
        if isinstance(menu, ContextualMenu) or menu is None:
            if self._path:
                menu = ContextualMenu() if menu is None else menu
                path = self.DefaultText if self._path is True else self._path
                menu.add_option('Open in File Manager', path, open_in_file_manager, None, 'cb_arg', False, False)

            self._right_click_menu = menu
            if menu and not self.RightClickMenu:
                self.RightClickMenu = ['-', []]
        else:
            self.RightClickMenu = menu

    @property
    def TKEntry(self):
        return self._tk_entry

    @TKEntry.setter
    def TKEntry(self, entry: Entry):
        self._tk_entry = entry
        if entry is not None:
            entry.bind('<FocusOut>', partial(_clear_selection, entry))  # Prevents ghost selections
            if self._link:
                entry.bind('<Control-Button-1>', self._open_link)

    @property
    def value(self):
        return self.get()

    def get_selection(self):
        entry = self.TKEntry
        selection = entry.selection_get()
        if not entry.selection_present():
            raise NotSelectionOwner
        return selection

    def _RightClickMenuCallback(self, event):
        if menu := self.right_click_menu:
            try:
                kwargs = {'selected': self.get_selection()}
            except (TclError, NotSelectionOwner):
                kwargs = {}
            if menu.show(event, self.TKEntry.master, **kwargs):
                return
        super()._RightClickMenuCallback(event)

    @property
    def disabled_readonly_background_color(self):
        if self.TKEntry['state'] == 'normal' and not self.Disabled:
            # print(f'Returning {self}.disabled_readonly_background_color = None')
            return None
        return self._disabled_readonly_background_color

    @disabled_readonly_background_color.setter
    def disabled_readonly_background_color(self, value):
        self._disabled_readonly_background_color = value

    @property
    def disabled_readonly_text_color(self):
        if self.TKEntry['state'] == 'normal' and not self.Disabled:
            # print(f'Returning {self}.disabled_readonly_text_color = None')
            return None
        return self._disabled_readonly_text_color

    @disabled_readonly_text_color.setter
    def disabled_readonly_text_color(self, value):
        self._disabled_readonly_text_color = value

    def update(self, *args, disabled=None, **kwargs):
        was_enabled = self.TKEntry['state'] == 'normal'
        super().update(*args, disabled=disabled, **kwargs)
        if disabled is not None:
            self.Disabled = disabled
        if self._dark and not was_enabled:
            if disabled is False:
                # bg = getattr(input_ele, 'disabled_readonly_background_color', input_ele.BackgroundColor)
                # fg = getattr(input_ele, 'disabled_readonly_text_color', input_ele.TextColor)
                self.TKEntry.configure(background=self.BackgroundColor, fg=self.TextColor)
                # self.TKEntry.configure(readonlybackground=self.BackgroundColor, disabledforeground=self.TextColor)
            else:
                if background_color := kwargs.get('background_color'):
                    # log.info(f'Setting {background_color=!r} for {self!r}')
                    self.TKEntry.configure(readonlybackground=background_color)
                if text_color := kwargs.get('text_color'):
                    # log.info(f'Setting {text_color=!r} for {self!r}')
                    self.TKEntry.configure(fg=text_color)

    def validated(self, valid: bool):
        if self._valid_value != valid:
            self._valid_value = valid
            if valid:
                self.update(background_color=self.TextColor, text_color=self.BackgroundColor)
            else:
                self.update(background_color='#781F1F', text_color='#FFFFFF')

    def _open_link(self, event):
        if (value := self.value) and value.startswith(('http://', 'https://')):
            webbrowser.open(value)


class NotSelectionOwner(Exception):
    pass


def _clear_selection(entry, event):
    entry.selection_clear()
