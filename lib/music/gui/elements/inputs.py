"""
Input elements for PySimpleGUI

:author: Doug Skrypa
"""

from PySimpleGUI import Input
from PySimpleGUI import theme, theme_input_background_color, theme_input_text_color

__all__ = ['DarkInput']


class DarkInput(Input):
    def __init__(self, *args, **kwargs):
        self._dark = 'dark' in theme().lower()
        if self._dark:
            kwargs.setdefault('background_color', theme_input_background_color())
            kwargs.setdefault('text_color', theme_input_text_color())
            kwargs.setdefault('disabled_readonly_background_color', '#a2a2a2')
            kwargs.setdefault('disabled_readonly_text_color', '#000000')
        super().__init__(*args, **kwargs)
        self._valid_value = True

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
