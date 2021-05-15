"""
Extended image elements for PySimpleGUI

:author: Doug Skrypa
"""

import logging
import math
from io import BytesIO
from pathlib import Path
from tkinter import Label
from typing import Union, Optional

from PIL import Image as ImageModule
from PIL.ImageTk import PhotoImage
from PIL.Image import Image as PILImage
from PySimpleGUI import Image

__all__ = ['ExtendedImage', 'ImageType']
log = logging.getLogger(__name__)
ImageType = Union[PILImage, bytes, Path, str, None]


class ExtendedImage(Image):
    def __init__(self, image: ImageType = None, popup_title: str = None, **kwargs):
        self.__in_popup = kwargs.pop('_in_popup', False)
        self._image = None
        super().__init__(**kwargs)
        self.image = image
        self._popup_title = popup_title
        self._current_size = self._get_size(*self.Size)

    @property
    def Widget(self):
        return self._widget

    @Widget.setter
    def Widget(self, tktext_label: Label):
        self._widget = tktext_label
        if self._image and tktext_label is not None:
            self.resize(*self.Size)
            if not self.__in_popup:
                self._widget.bind('<Button-1>', self.handle_click)

    @property
    def image(self) -> Optional[PILImage]:
        return self._image

    @image.setter
    def image(self, data: ImageType):
        if data is None or isinstance(data, PILImage):
            self._image = data
        elif isinstance(data, bytes):
            self._image = ImageModule.open(BytesIO(data))
        elif isinstance(data, (Path, str)):
            with open(data, 'rb') as f:
                data = BytesIO(f.read())  # Using the file directly results in closed file seek errors on resize
            self._image = ImageModule.open(data)
        else:
            raise TypeError(f'Image must be bytes, None, or a PIL.Image.Image - found {type(data)}')

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

    def _get_size(self, width: int, height: int):
        if (image := self._image) is not None:
            return calculate_resize(*image.size, width, height)
        return width, height

    def handle_click(self, event):
        from ..popups.image import ImageView

        ImageView(self._image, self._popup_title).get_result()


def calculate_resize(src_w, src_h, new_w, new_h):
    """Copied logic from :meth:`PIL.Image.Image.thumbnail`"""
    x, y = map(math.floor, (new_w, new_h))
    aspect = src_w / src_h
    if x / y >= aspect:
        x = round_aspect(y * aspect, key=lambda n: abs(aspect - n / y))
    else:
        y = round_aspect(x / aspect, key=lambda n: 0 if n == 0 else abs(aspect - x / n))
    return x, y


def round_aspect(number, key):
    return max(min(math.floor(number), math.ceil(number), key=key), 1)
