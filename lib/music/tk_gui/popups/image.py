"""
Tkinter GUI image popups

:author: Doug Skrypa
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional, Union

from PIL.Image import MIME

from ..elements.images import AnimatedType, Image, Animation, ClockImage, SpinnerImage, get_size
from ..positioning import positioner
from ..images import as_image
from .base import Popup

if TYPE_CHECKING:
    from tkinter import Event
    from ..typing import XY, Layout, ImageType

__all__ = ['ImagePopup', 'AnimatedPopup', 'SpinnerPopup', 'ClockPopup']
log = logging.getLogger(__name__)


class ImagePopup(Popup):
    _empty: bool = True
    orig_size: XY
    _last_size: XY
    gui_image: Image

    def __init__(self, image: Union[ImageType, AnimatedType], title: str = None, **kwargs):
        binds = kwargs.setdefault('binds', {})
        binds['SIZE_CHANGED'] = self.handle_size_changed
        kwargs.setdefault('margins', (0, 0))
        kwargs.setdefault('bind_esc', True)
        kwargs.setdefault('keep_on_top', False)
        kwargs.setdefault('can_minimize', True)
        super().__init__(title=title or 'Image', **kwargs)
        self._set_image(image)

    def get_layout(self) -> Layout:
        return [[self.gui_image]]

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__}[title={self.title!r}, orig={self.orig_size}, empty: {self._empty}]>'

    def _set_image(self, image: ImageType):
        image = as_image(image)
        self._empty = image is None
        self.orig_size = image.size if image else (0, 0)
        self._last_size = init_size = self._init_size()
        self.gui_image = Image(image, size=init_size, pad=(2, 2))
        if image:
            log.debug(f'{self}: Displaying {image=} with {image.format=} mime={MIME.get(image.format)!r}')

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
        image = self.gui_image
        px, py = image.pad
        new_size = (new_w - px * 2 - 2, new_h - py * 2 - 2)
        new_img = image.target_size(*new_size)
        if new_img != image.size:
            # log.debug(
            #     f'Resizing from old_win={self._last_size} to new_win={(new_w, new_h)},'
            #     f' old_img={image.size} to {new_img=}, using {new_size=} due to event for {self}'
            # )
            return new_size
        # log.debug(
        #     f'Not resizing: old_win={self._last_size}, new_win={(new_w, new_h)},'
        #     f' old_img={image.size} == {new_img=}, using {new_size=} for {self}'
        # )
        return None

    def handle_size_changed(self, event: Event, size: XY):
        if self._empty or self._last_size == size:
            # log.debug(f'Ignoring config {event=} for {self} @ {monotonic()}')
            return
        # log.debug(f'Handling config {event=} for {self}')
        if new_size := self._get_new_size(*size):
            self._last_size = size
            self.gui_image.resize(*new_size)
            self.window.set_title(self.title)


class AnimatedPopup(ImagePopup):
    def _set_image(self, image: AnimatedType):
        # log.debug(f'_set_image: {image=}')
        self.orig_size = get_size(image) if image else (0, 0)
        self._last_size = init_size = self._init_size()
        self.gui_image = animation = Animation(image, size=init_size, pad=(2, 2))
        self._empty = animation.size == (0, 0)


class SpinnerPopup(AnimatedPopup):
    def __init__(self, *args, img_size: XY = None, **kwargs):
        self._img_size = img_size
        super().__init__(None, *args, **kwargs)

    def _set_image(self, image: None):
        self._empty = False
        self.orig_size = self._img_size or SpinnerImage.DEFAULT_SIZE
        self._last_size = init_size = self._init_size()
        self.gui_image = SpinnerImage(size=init_size, pad=(2, 2))


class ClockPopup(AnimatedPopup):
    def __init__(self, *args, img_size: XY = None, toggle_slim_on_click: bool = False, **kwargs):
        self._img_size = img_size
        self._toggle_slim_on_click = toggle_slim_on_click
        super().__init__(None, *args, **kwargs)

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
