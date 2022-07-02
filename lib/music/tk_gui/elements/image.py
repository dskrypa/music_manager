"""
Tkinter GUI images

:author: Doug Skrypa
"""

from __future__ import annotations

import logging
import tkinter.constants as tkc
from functools import cached_property
from pathlib import Path
from tkinter import Tk, Toplevel, Frame, PhotoImage, Widget, Label
from typing import TYPE_CHECKING, Optional, Callable, Union, Iterable

from PIL.ImageTk import PhotoImage
from PIL.Image import Image as PILImage, Resampling

from ds_tools.images.utils import ImageType, Size, as_image, calculate_resize

from .element import Element

if TYPE_CHECKING:
    from ..pseudo_elements import Row

__all__ = ['Image']
log = logging.getLogger(__name__)


class Image(Element):
    # _image: Optional[PILImage] = None
    animated: bool = False

    def __init_subclass__(cls, animated: bool = False):
        cls.animated = animated

    def __init__(self, image: ImageType = None, **kwargs):
        super().__init__(**kwargs)
        self._image = GuiImage(image)

    # @property
    # def image(self) -> Optional[PILImage]:
    #     return self._image
    #
    # @image.setter
    # def image(self, data: ImageType):
    #     self._image = as_image(data)
    #     # if self.widget is not None:
    #     #     self.resize()

    def pack_into(self, row: Row):
        style = self.style
        try:
            width, height = self.size
        except TypeError:
            width, height = None, None

        image, width, height = self._image.as_size(width, height)
        # log.debug(f'Packing {image=} into row with {width=}, {height=}')
        if image:
            image = PhotoImage(image)
            kwargs = {'image': image}
        else:
            kwargs = {}
        self.widget = label = Label(
            row.frame,
            width=width,
            height=height,
            bd=style.border_width,
            background=style.bg.default,
            **kwargs
        )
        label.image = image
        label.pack(side=tkc.LEFT, expand=False, fill=tkc.NONE, **self.pad_kw)  # TODO: Verify
        if not self._visible:
            label.pack_forget()


class GuiImage:
    __slots__ = ('src_image', 'current', 'src_size', 'size')

    def __init__(self, image: ImageType):
        image = as_image(image)
        # log.debug(f'Loaded image={image!r}')
        self.src_image: Optional[PILImage] = image
        self.current: Optional[PILImage] = image
        try:
            size = image.size
        except AttributeError:  # image is None
            size = (0, 0)
        self.src_size = size
        self.size = size

    def _normalize(self, width: Optional[int], height: Optional[int]) -> Size:
        if width is None:
            width = self.size[0]
        if height is None:
            height = self.size[1]
        return width, height

    def as_size(self, width: Optional[int], height: Optional[int]) -> tuple[Optional[PILImage], int, int]:
        width, height = self._normalize(width, height)
        if (current := self.current) is None:
            return None, width, height

        cur_width, cur_height = self.size
        if cur_width == width and cur_height == height:
            return current, width, height
        elif cur_width >= width and cur_height >= height:
            src = current
            dst_width, dst_height = calculate_resize(cur_width, cur_height, width, height)
        else:
            src = self.src_image
            dst_width, dst_height = calculate_resize(*self.src_size, width, height)

        dst_size = (dst_width, dst_height)
        try:
            self.current = image = src.resize(dst_size, Resampling.LANCZOS)
        except OSError as e:
            log.warning(f'Error resizing image={src}: {e}')
            return src, width, height
        else:
            self.size = dst_size
            return image, dst_width, dst_height
