"""
Tkinter GUI images

:author: Doug Skrypa
"""

from __future__ import annotations

import logging
from functools import cached_property
from pathlib import Path
from tkinter import Tk, Toplevel, Frame, PhotoImage, Widget
from typing import TYPE_CHECKING, Optional, Callable, Union, Iterable

from PIL.ImageTk import PhotoImage
from PIL.Image import Image as PILImage, Resampling

from ds_tools.images.utils import ImageType, Size, as_image, calculate_resize

from .style import Style, Font
from .core import Element, Inheritable, Row

__all__ = ['Image']
log = logging.getLogger(__name__)


class Image(Element):
    _image: Optional[PILImage] = None
    animated: bool = False

    def __init_subclass__(cls, animated: bool = False):
        cls.animated = animated

    def __init__(self, image: Optional[PILImage] = None, **kwargs):
        super().__init__(**kwargs)
        self.image = image

    @property
    def image(self) -> Optional[PILImage]:
        return self._image

    @image.setter
    def image(self, data: ImageType):
        self._image = as_image(data)
        # if self.widget is not None:
        #     self.resize()

    def pack_into(self, row: Row):
        self.parent = row
        # TODO
