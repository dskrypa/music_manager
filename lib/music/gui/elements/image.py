"""
Extended image elements for PySimpleGUI

:author: Doug Skrypa
"""

import logging
from itertools import count
from tkinter import Label
from typing import Optional, Callable

from PIL.ImageTk import PhotoImage
from PIL.Image import Image as PILImage
from PySimpleGUI import Image

from ...common.images import ImageType, as_image, calculate_resize

__all__ = ['ExtendedImage', 'Spacer']
log = logging.getLogger(__name__)


class ExtendedImage(Image):
    def __init__(
        self,
        image: ImageType = None,
        popup_title: str = None,
        init_callback: Callable = None,
        bind_click: bool = True,
        **kwargs
    ):
        self._bind_click = bind_click
        self._image = None
        super().__init__(**kwargs)
        self.image = image
        self._popup_title = popup_title
        self._current_size = self._get_size(*self.Size)
        self._init_callback = init_callback

    @property
    def Widget(self) -> Optional[Label]:
        return self._widget

    @Widget.setter
    def Widget(self, tktext_label: Label):
        self._widget = tktext_label
        if tktext_label is not None:
            if self._image:
                self.resize(*self.Size)
            if callback := self._init_callback:
                callback(self)

    @property
    def image(self) -> Optional[PILImage]:
        return self._image

    @image.setter
    def image(self, data: ImageType):
        self._image = as_image(data)
        if self._widget is not None:
            self.resize(*self._current_size)

    @property
    def current_size(self):
        return self._current_size

    def resize(self, width: int, height: int):
        if self._image:
            new_w, new_h = self._get_size(width, height)
            # self.log.log(19, f'Resizing image from {img_w}x{img_h} to {new_w}x{new_h}')
            try:
                image = PhotoImage(self._image.resize((new_w, new_h), 1))  # 1 = ANTIALIAS
            except OSError as e:
                log.warning(f'Error resizing {self._image}: {e}')
            else:
                self._current_size = (new_w, new_h)
                self._widget.configure(image=image, width=new_w, height=new_h)
                self._widget.image = image
                self._widget.pack(padx=self.pad_used[0], pady=self.pad_used[1])
                if self._bind_click:
                    self._widget.bind('<Button-1>', self.handle_click)

    def _get_size(self, width: int, height: int):
        if (image := self._image) is not None:
            return calculate_resize(*image.size, width, height)
        return width, height

    def handle_click(self, event):
        from ..popups.image import ImageView

        ImageView(self._image, self._popup_title).get_result()


class Spacer(Image):
    _count = count()

    def __init__(self, *args, key=None, **kwargs):
        key = key or f'spacer::{next(self._count)}'
        kwargs.setdefault('pad', (0, 0))
        super().__init__(*args, key=key, **kwargs)
