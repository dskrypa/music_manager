"""
Tkinter GUI image popups

:author: Doug Skrypa
"""

from __future__ import annotations

import logging
from time import monotonic
from typing import TYPE_CHECKING, Optional, Union

from PIL.Image import MIME

from ds_tools.images.utils import ImageType, as_image

from ..core import Window
from ..elements.image import AnimatedType, Image, Animation, ClockImage, SpinnerImage, get_size
from ..positioning import positioner

if TYPE_CHECKING:
    from tkinter import Event
    from ..utils import XY

__all__ = ['ImagePopup', 'AnimatedPopup']
log = logging.getLogger(__name__)


class ImagePopup:
    _empty: bool = True
    orig_size: XY
    _last_size: XY
    gui_image: Image

    def __init__(self, image: Union[ImageType, AnimatedType], title: str = None, parent: Window = None, **kwargs):
        self.parent = parent
        self._title = title or 'Image'
        self._set_image(image)
        self._last_resize = 0
        binds = kwargs.setdefault('binds', {})
        binds.setdefault('<Escape>', 'exit')
        binds['<Configure>'] = self.handle_config_changed
        kwargs.setdefault('margins', (0, 0))
        self.window = Window(self.title, [[self.gui_image]], **kwargs)

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__}[title={self.title!r}, orig={self.orig_size}, empty: {self._empty}]>'

    def _set_image(self, image: ImageType):
        image = as_image(image)
        self._empty = bool(image)
        if image:
            log.debug(f'Displaying {image=} with {image.format=} mime={MIME.get(image.format)!r}')
        self.orig_size = image.size if image else (0, 0)
        self._last_size = init_size = self._init_size()
        self.gui_image = Image(image, size=init_size, pad=(2, 2))

    def _init_size(self) -> XY:
        width, height = self.orig_size
        if parent := self.parent:
            if monitor := positioner.get_monitor(*parent.position):
                return min(monitor.width - 70, width or 0), min(monitor.height - 70, height or 0)
        return width, height

    @property
    def title(self) -> str:
        try:
            img_w, img_h = self.gui_image.size
        except TypeError:
            return self._title
        else:
            src_w, src_h = self.orig_size
            return f'{self._title} ({img_w}x{img_h}, {img_w / src_w if src_w else 1:.0%})'

    @title.setter
    def title(self, value: str):
        self._title = value

    def _get_new_size(self, new_w: int, new_h: int) -> Optional[XY]:
        last_w, last_h = self._last_size
        target_w = new_w - 4
        target_h = new_h - 6
        # log.debug(f'{last_w=} {last_h=}  |  {target_w=} {target_h=}')
        if not ((last_h == new_h and target_w < new_w) or (last_w == new_w and target_h < new_h)):
            return target_w, target_h
        return None

    def handle_config_changed(self, event: Event):
        size = (event.width, event.height)
        # log.debug(f'Handling config {event=} with type={event.type!r} {size=}')
        log.debug(f'Handling config {event=} for {self}')
        if self._empty or self._last_size == size or monotonic() - self._last_resize < 0.15:
            return
        if new_size := self._get_new_size(*size):
            self._last_size = new_size
            self.gui_image.resize(*new_size)
            self.window.set_title(self.title)
            self._last_resize = monotonic()

    def run(self):
        self.window.run()


class AnimatedPopup(ImagePopup):
    def _set_image(self, image: AnimatedType):
        # log.debug(f'_set_image: {image=}')
        self.orig_size = get_size(image) if image else (0, 0)
        self._last_size = init_size = self._init_size()
        self.gui_image = animation = Animation(image, size=init_size, pad=(2, 2))
        self._empty = animation.size == (0, 0)
