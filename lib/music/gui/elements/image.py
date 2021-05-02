"""
Image elements for PySimpleGUI

:author: Doug Skrypa
"""

import math
from io import BytesIO

from PIL import Image as ImageModule
from PIL.ImageTk import PhotoImage
from PIL.Image import Image as PILImage
from PySimpleGUI import Image
from tkinter import Label

__all__ = ['ExtendedImage']


class ExtendedImage(Image):
    def __init__(
        self, *args, data: bytes = None, image: PILImage = None, border_width: int = 1, background_color=None, **kwargs
    ):
        if image and data:
            raise ValueError('Only one of image / data are accepted')
        super().__init__(*args, **kwargs)
        self._image = image if image else ImageModule.open(BytesIO(data))
        self._border_width = border_width
        self._background_color = background_color
        self._widget = None

    @property
    def Widget(self):
        return self._widget

    @Widget.setter
    def Widget(self, tktext_label: Label):
        if tktext_label is None:
            return
        elif self._image:
            width, height = self.Size
            image = PhotoImage(self.resize(width, height))
            tktext_label.configure(image=image, width=width, height=height)
            tktext_label.image = image
            tktext_label.pack(padx=self.pad_used[0], pady=self.pad_used[1])
        self._widget = tktext_label

    def resize(self, width: int, height: int):
        image = self._image
        old_w, old_h = image.size
        new_w, new_h = calculate_resize(old_w, old_h, (width, height))
        # self.log.log(19, f'Resizing image from {img_w}x{img_h} to {new_w}x{new_h}')
        return image.resize((new_w, new_h), 1)  # 1 = ANTIALIAS


def calculate_resize(src_w, src_h, new_size):
    """Copied logic from :meth:`PIL.Image.Image.thumbnail`"""
    x, y = map(math.floor, new_size)
    aspect = src_w / src_h
    if x / y >= aspect:
        x = round_aspect(y * aspect, key=lambda n: abs(aspect - n / y))
    else:
        y = round_aspect(x / aspect, key=lambda n: 0 if n == 0 else abs(aspect - x / n))
    return x, y


def round_aspect(number, key):
    return max(min(math.floor(number), math.ceil(number), key=key), 1)
