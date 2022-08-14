"""
Tkinter GUI Clock

:author: Doug Skrypa
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..elements.images import ClockImage
from ..popups.image import AnimatedPopup
from ..style import Style
from ..window import Window

if TYPE_CHECKING:
    from tkinter import Event
    from ..typing import XY

__all__ = ['ClockView']


class ClockView(AnimatedPopup):
    gui_image: ClockImage

    def __init__(self, img_size: XY = None, **kwargs):
        self._img_size = img_size
        self._toggle_slim_on_click = '<Button-2>'
        kwargs.setdefault('title', 'Clock')
        kwargs.setdefault('config_name', self.__class__.__name__)
        kwargs.setdefault('margins', (0, 0))
        kwargs.setdefault('style', Style(bg='#000000'))
        kwargs.setdefault('alpha_channel', 0.8)
        kwargs.setdefault('grab_anywhere', True)
        kwargs.setdefault('no_title_bar', True)
        binds = kwargs.setdefault('binds', {})
        binds.setdefault('<Button-3>', self.toggle_title)
        binds.setdefault('<KeyPress-plus>', self.increase_size)
        binds.setdefault('<KeyPress-minus>', self.decrease_size)
        super().__init__(None, **kwargs)

    def prepare_window(self) -> Window:
        return Window(self.get_layout(), title=self.title, is_popup=False, **self.window_kwargs)

    def toggle_title(self, event: Event):
        self.window.toggle_title_bar()

    def increase_size(self, event: Event):
        width, height = self.window.size
        self.window.size = (width + 10, height + 10)

    def decrease_size(self, event: Event):
        image = self.gui_image
        width, height = image.clock.time_size()
        image.resize(width, height - 10)

    def _set_image(self, image: None):
        self._empty = False
        kwargs = {'toggle_slim_on_click': self._toggle_slim_on_click, 'pad': (2, 2)}
        if img_size := self._img_size:
            self.orig_size = img_size
            self._last_size = init_size = self._init_size()
            self.gui_image = ClockImage(img_size=init_size, **kwargs)
        else:
            self.gui_image = ClockImage(**kwargs)
            self.orig_size = self._last_size = self.gui_image.size


if __name__ == '__main__':
    ClockView().run()
