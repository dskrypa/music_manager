"""
Tkinter GUI images

:author: Doug Skrypa
"""

from __future__ import annotations

import logging
import tkinter.constants as tkc
from datetime import datetime, timedelta
from inspect import Signature
from pathlib import Path
from tkinter import Label, TclError, Event
from typing import TYPE_CHECKING, Optional, Any, Union

from PIL.Image import Image as PILImage, Resampling
from PIL.ImageSequence import Iterator as FrameIterator
from PIL.ImageTk import PhotoImage

from ds_tools.images.animated.cycle import FrameCycle, PhotoImageCycle
from ds_tools.images.animated.spinner import Spinner
from ds_tools.images.lcd import SevenSegmentDisplay
from ds_tools.images.utils import ImageType, Size, as_image, calculate_resize

from ..style import Style, StyleSpec
from .element import Element

if TYPE_CHECKING:
    from ..pseudo_elements import Row
    from ..typing import XY

__all__ = ['Image', 'Animation', 'SpinnerImage', 'ClockImage', 'get_size']
log = logging.getLogger(__name__)

AnimatedType = Union[PILImage, Spinner, Path, str, '_ClockCycle']
_Image = Optional[Union[PILImage, PhotoImage]]
ImageAndSize = tuple[_Image, int, int]
ImageCycle = Union[FrameCycle, '_ClockCycle']


class Image(Element):
    widget: Label
    animated: bool = False

    def __init_subclass__(cls, animated: bool = None):
        if animated is not None:
            cls.animated = animated

    def __init__(self, image: ImageType = None, **kwargs):
        super().__init__(**kwargs)
        self._image = _GuiImage(image)

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
        # log.debug(f'Packing {image=} into row with {width=}, {height=}')
        style = self.style
        kwargs = {'image': image} if image else {}
        self.size = (width, height)
        self.widget = label = Label(
            row.frame,
            width=width,
            height=height,
            bd=style.border_width,
            background=style.bg.default,
            **kwargs
        )
        label.image = image
        # label.pack(side=tkc.LEFT, expand=False, fill=tkc.NONE, **self.pad_kw)
        self.pack_widget()

    def _re_pack(self, image: _Image, width: int, height: int):
        self.size = (width, height)
        widget = self.widget
        widget.configure(image=image, width=width, height=height)

        widget.image = image
        widget.pack(**self.pad_kw)

    def target_size(self, width: int, height: int) -> Size:
        return self._image.target_size(width, height)

    def resize(self, width: int, height: int):
        image, width, height = self._image.as_size(width, height)
        self._re_pack(image, width, height)


class Animation(Image, animated=True):
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

    def target_size(self, width: int, height: int) -> Size:
        try:
            size = self.__image.size
        except AttributeError:
            size = self.size
        return calculate_resize(*size, width, height)

    def resize(self, width: int, height: int):
        # self.size = size = (width, height)
        self.image_cycle = image_cycle = self._resize_cycle((width, height))
        image = self.__image
        try:
            width, height = size = image.size
        except AttributeError:
            width, height = size = image.width, image.height

        # self.size = size
        frame, delay = next(image_cycle)
        self._re_pack(frame, width, height)
        if self._run:
            self._cancel()
            self._next_id = self.widget.after(delay, self.next)

    def _resize_cycle(self, size: XY) -> ImageCycle:
        return normalize_image_cycle(self.__image, size, self.image_cycle.n)

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

    def _cancel(self):
        if next_id := self._next_id:
            try:
                self.widget.after_cancel(next_id)
            except (TclError, RuntimeError) as e:
                log.debug(f'Error canceling next animation step: {e}')
            self._next_id = None

    def pause(self):
        self._run = False
        self._cancel()

    def resume(self):
        self._run = True
        self.next()


class SpinnerImage(Animation):
    _spinner_keys = set(Signature.from_callable(Spinner).parameters.keys())
    DEFAULT_SIZE = (200, 200)
    DEFAULT_KWARGS = {'frame_fade_pct': 0.01, 'frame_duration_ms': 20, 'frames_per_spoke': 1}

    def __init__(self, **kwargs):
        spinner_kwargs = _extract_kwargs(kwargs, self._spinner_keys, self.DEFAULT_KWARGS)
        size = spinner_kwargs.setdefault('size', self.DEFAULT_SIZE)
        spinner = Spinner(**spinner_kwargs)
        super().__init__(spinner, size=size, **kwargs)

    def target_size(self, width: int, height: int) -> Size:
        # TODO: Add support for keeping aspect ratio
        return width, height


class _ClockCycle:
    __slots__ = ('clock', 'show_seconds', 'delay', 'last_time', '_last_frame', 'n')
    SECOND = timedelta(seconds=1)

    def __init__(self, clock: SevenSegmentDisplay, seconds: bool = True):
        self.clock = clock
        self.show_seconds = seconds
        self.delay = 200 if seconds else 1000
        self.last_time = datetime.now() - self.SECOND
        self._last_frame = None
        self.n = 0

    def __next__(self):
        now = datetime.now()
        if now.second != self.last_time.second:
            self.last_time = now
            self._last_frame = frame = PhotoImage(self.clock.draw_time(now, self.show_seconds))
        else:
            frame = self._last_frame

        return frame, self.delay

    back = __next__

    @property
    def size(self) -> XY:
        clock = self.clock
        return clock.width, clock.height


class ClockImage(Animation):
    image_cycle: _ClockCycle
    _clock_keys = set(Signature.from_callable(SevenSegmentDisplay).parameters.keys())
    DEFAULT_KWARGS = {'bar_pct': 0.2, 'width': 40}

    def __init__(
        self,
        slim: bool = False,
        img_size: XY = None,
        seconds: bool = True,
        style: StyleSpec = None,
        toggle_slim_on_click: bool = False,
        **kwargs,
    ):
        clock_kwargs = _extract_kwargs(kwargs, self._clock_keys, self.DEFAULT_KWARGS)
        self._slim = slim
        self.clock = clock = SevenSegmentDisplay(**clock_kwargs)
        if img_size is not None:
            clock.resize(clock.calc_width(calculate_resize(*clock.time_size(seconds), *img_size)[1]) - 1)
        if toggle_slim_on_click:
            kwargs['left_click_cb'] = self.toggle_slim
        kwargs.setdefault('pad', (0, 0))
        kwargs.setdefault('size', clock.time_size(seconds))
        super().__init__(_ClockCycle(clock, seconds), style=style or Style(bg='black'), **kwargs)

    def toggle_slim(self, event: Event = None):
        slim = self._slim
        clock = self.clock
        clock.resize(bar_pct=(clock.bar_pct * (2 if slim else 0.5)), preserve_height=True)
        self._slim = not slim
        self.image_cycle.last_time -= _ClockCycle.SECOND

    def _resize_cycle(self, size: XY) -> ImageCycle:
        # clock = self.clock
        # image_cycle = self.image_cycle
        self.clock.resize(self.target_size(*size)[0])
        return self.image_cycle
        # clock.resize(clock.calc_width(calculate_resize(*clock.time_size(image_cycle.show_seconds), *size)[1]) - 1)
        # return image_cycle

    def target_size(self, width: int, height: int) -> Size:
        clock = self.clock
        image_cycle = self.image_cycle
        width = clock.calc_width(calculate_resize(*clock.time_size(image_cycle.show_seconds), width, height)[1]) - 1
        height = 2 * width - clock.bar
        return width, height


class _GuiImage:
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

    def target_size(self, width: Optional[int], height: Optional[int]) -> Size:
        width, height = self._normalize(width, height)
        cur_width, cur_height = self.size
        if self.current is None or (cur_width == width and cur_height == height):
            return width, height
        # elif cur_width >= width and cur_height >= height:
        #     return calculate_resize(cur_width, cur_height, width, height)
        else:
            return calculate_resize(*self.src_size, width, height)

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


def normalize_image_cycle(image: AnimatedType, size: Size = None, last_frame_num: int = 0) -> ImageCycle:
    if isinstance(image, Spinner):
        if size:
            image.resize(size)
        frame_cycle = image.cycle(PhotoImage)
    elif isinstance(image, _ClockCycle):
        frame_cycle = image
        if size:
            clock = frame_cycle.clock
            clock.resize(clock.calc_width(size[1]) - 1)
            frame_cycle.last_time -= frame_cycle.SECOND
    else:
        try:
            path = _get_path(image)
        except ValueError:
            image = as_image(image)
            frame_cycle = FrameCycle(tuple(FrameIterator(image)), PhotoImage)
        else:
            frame_cycle = PhotoImageCycle(path)

        # TODO: Likely need a different lib for gif resize
        # if size and size != get_size(image):
        #     frame_cycle = frame_cycle.resized(*size)

    # elif isinstance(image, (Path, str)):
    #     frame_cycle = PhotoImageCycle(Path(image).expanduser())
    #     if size:
    #         log.debug(f'Resizing {frame_cycle=} to {size=}')
    #         frame_cycle = frame_cycle.resized(*size)
    # else:  # TODO: PhotoImageCycle will not result in expected resize behavior...
    #     if path := getattr(image, 'filename', None) or getattr(getattr(image, 'fp', None), 'name', None):
    #         frame_cycle = PhotoImageCycle(Path(path))
    #         if size:
    #             log.debug(f'Resizing {frame_cycle=} to {size=}')
    #             frame_cycle = frame_cycle.resized(*size)
    #     else:
    #         raise ValueError(f'Unexpected image type for {image=}')
    #         # image = AnimatedGif(image)
    #         # if size:
    #         #     image = image.resize(size, 1)
    #         # frame_cycle = image.cycle(PhotoImage)

    frame_cycle.n = last_frame_num
    return frame_cycle


def _get_path(image: ImageType) -> Path:
    if isinstance(image, Path):
        return image
    elif isinstance(image, str):
        return Path(image).expanduser()
    elif path := getattr(image, 'filename', None) or getattr(getattr(image, 'fp', None), 'name', None):
        return Path(path)
    raise ValueError(f'Unexpected image type for {image=}')


def get_size(image: Union[AnimatedType, SevenSegmentDisplay]) -> XY:
    if isinstance(image, Spinner):
        return image.size
    elif isinstance(image, SevenSegmentDisplay):
        return image.width, image.height
    image = as_image(image)
    return image.size


def _extract_kwargs(kwargs: dict[str, Any], keys: set[str], defaults: dict[str, Any]) -> dict[str, Any]:
    extracted = {key: kwargs.pop(key) for key in keys if key in kwargs}
    for key, val in defaults.items():
        extracted.setdefault(key, val)

    return extracted
