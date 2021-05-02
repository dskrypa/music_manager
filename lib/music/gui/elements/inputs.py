"""
Input elements for PySimpleGUI

:author: Doug Skrypa
"""

from functools import partial
from typing import Callable

from PySimpleGUI import Input, theme, theme_input_background_color, theme_input_text_color
from tkinter import TclError, Menu, Entry

__all__ = ['DarkInput']
MenuDict = dict[str, str]


class DarkInput(Input):
    TKEntry: Entry

    def __init__(self, *args, right_click_selection: tuple[MenuDict, Callable] = None, **kwargs):
        """
        :param args: Positional arguments to pass to :class:`PySimpleGUI.Input`
        :param right_click_selection: Tuple of ({key: format string}, callback), where the format string values will be
          used to create menu entries with the selected text, and the callback should accept 2 positional arguments:
          key and selected text.
        :param kwargs: Keyword arguments to pass to :class:`PySimpleGUI.Input`
        """
        self._dark = 'dark' in theme().lower()
        if self._dark:
            kwargs.setdefault('background_color', theme_input_background_color())
            kwargs.setdefault('text_color', theme_input_text_color())
            kwargs.setdefault('disabled_readonly_background_color', '#a2a2a2')
            kwargs.setdefault('disabled_readonly_text_color', '#000000')
        super().__init__(*args, **kwargs)
        self._valid_value = True
        self.right_click_selection = right_click_selection

    @property
    def right_click_selection(self):
        return self._right_click_selection

    @right_click_selection.setter
    def right_click_selection(self, value: tuple[MenuDict, Callable]):
        self._right_click_selection = value
        if value and not self.RightClickMenu:
            self.RightClickMenu = ['-', []]

    def _RightClickMenuCallback(self, event):
        print(event)
        if self.right_click_selection:
            try:
                selected = self.TKEntry.selection_get()
            except TclError:
                super()._RightClickMenuCallback(event)
            else:
                menu_dict, callback = self.right_click_selection
                menu = Menu(self.TKEntry.master, tearoff=0)
                for key, fmt_str in menu_dict.items():
                    menu.add_command(label=fmt_str.format(selected), command=partial(callback, key, selected))
                try:
                    menu.tk_popup(event.x_root, event.y_root)
                finally:
                    menu.grab_release()
        else:
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
