"""
Tkinter GUI images

:author: Doug Skrypa
"""

from __future__ import annotations

import logging
import tkinter.constants as tkc
from functools import cached_property
from pathlib import Path
from tkinter import Label, TclError, Event
from typing import TYPE_CHECKING, Optional, Callable, Union, Iterable

from PIL.ImageTk import PhotoImage
from PIL.Image import Image as PILImage, Resampling

from ds_tools.images.animated.cycle import FrameCycle, PhotoImageCycle
from ds_tools.images.animated.gif import AnimatedGif
from ds_tools.images.animated.spinner import Spinner
from ds_tools.images.lcd import SevenSegmentDisplay
from ds_tools.images.utils import ImageType, Size, as_image, calculate_resize

from .element import Element

if TYPE_CHECKING:
    from ..pseudo_elements import Row

__all__ = ['Image', 'Animation']
log = logging.getLogger(__name__)

AnimatedType = Union[PILImage, Spinner, Path, str]
_Image = Optional[Union[PILImage, PhotoImage]]
ImageAndSize = tuple[_Image, int, int]


class Image(Element):
    animated: bool = False

    def __init_subclass__(cls, animated: bool = None):
        if animated is not None:
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
        try:
            width, height = self.size
        except TypeError:
            width, height = None, None

        image, width, height = self._image.as_size(width, height)
        self._pack_into(row, image, width, height)

    def _pack_into(self, row: Row, image: _Image, width: int, height: int):
        log.debug(f'Packing {image=} into row with {width=}, {height=}')
        style = self.style
        kwargs = {'image': image} if image else {}
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


class Animation(Image, animated=True):
    widget: Label
    image_cycle: FrameCycle

    def __init__(self, image: AnimatedType, last_frame_num: int = 0, paused: bool = False, **kwargs):
        Element.__init__(self, **kwargs)
        self.__image = image
        self._last_frame_num = last_frame_num
        self._next_id = None
        self._run = not paused

    @property
    def paused(self):
        return not self._run

    def pack_into(self, row: Row):
        # log.debug(f'pack_into: {self.size=}')
        self.image_cycle = image_cycle = normalize_image_cycle(self.__image, self.size, self._last_frame_num)
        # log.debug(f'Prepared {len(image_cycle)} frames')
        frame, delay = next(image_cycle)
        try:
            width, height = self.size
        except TypeError:
            width = frame.width()
            height = frame.height()
            self.size = (width, height)

        self._pack_into(row, frame, width, height)
        if self._run:
            self._next_id = self.widget.after(delay, self.next)

    def next(self):
        frame, delay = next(self.image_cycle)
        width, height = self.size
        self.widget.configure(image=frame, width=width, height=height)
        if self._run:
            self._next_id = self.widget.after(delay, self.next)

    def previous(self):
        frame, delay = self.image_cycle.back()
        width, height = self.size
        self.widget.configure(image=frame, width=width, height=height)
        if self._run:
            self._next_id = self.widget.after(delay, self.previous)

    def pause(self):
        self._run = False
        if next_id := self._next_id:
            try:
                self.widget.after_cancel(next_id)
            except (TclError, RuntimeError) as e:
                log.debug(f'Error canceling next animation step: {e}')
            self._next_id = None

    def resume(self):
        self._run = True
        self.next()


class GuiImage:
    __slots__ = ('src_image', 'current', 'current_tk', 'src_size', 'size')

    def __init__(self, image: ImageType):
        image = as_image(image)
        # log.debug(f'Loaded image={image!r}')
        self.src_image: Optional[PILImage] = image
        self.current: Optional[PILImage] = image
        self.current_tk: Optional[PhotoImage] = None
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

    def as_size(self, width: Optional[int], height: Optional[int]) -> ImageAndSize:
        width, height = self._normalize(width, height)
        if (current := self.current) is None:
            return None, width, height

        cur_width, cur_height = self.size
        if cur_width == width and cur_height == height:
            if not (current_tk := self.current_tk):
                self.current_tk = current_tk = PhotoImage(current)
            return current_tk, width, height
        elif cur_width >= width and cur_height >= height:
            src = current
            dst_width, dst_height = calculate_resize(cur_width, cur_height, width, height)
        else:
            src = self.src_image
            dst_width, dst_height = calculate_resize(*self.src_size, width, height)

        dst_size = (dst_width, dst_height)
        try:
            self.current = image = src.resize(dst_size, Resampling.LANCZOS)
            self.current_tk = tk_image = PhotoImage(image)
        except OSError as e:
            log.warning(f'Error resizing image={src}: {e}')
            return src, width, height
        else:
            self.size = dst_size
            return tk_image, dst_width, dst_height


def normalize_image_cycle(image: AnimatedType, size: Size = None, last_frame_num: int = 0) -> FrameCycle:
    if isinstance(image, Spinner):
        if size:
            image.resize(size)
        frame_cycle = image.cycle(PhotoImage)
    elif isinstance(image, (Path, str)):
        frame_cycle = PhotoImageCycle(Path(image).expanduser())
    else:  # TODO: PhotoImageCycle will not result in expected resize behavior...
        if path := getattr(image, 'filename', None) or getattr(getattr(image, 'fp', None), 'name', None):
            frame_cycle = PhotoImageCycle(Path(path))
        else:
            image = AnimatedGif(image)
            if size:
                image = image.resize(size, 1)
            frame_cycle = image.cycle(PhotoImage)

    frame_cycle.n = last_frame_num
    return frame_cycle
