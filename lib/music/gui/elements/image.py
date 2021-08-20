"""
Extended image elements for PySimpleGUI

:author: Doug Skrypa
"""

import logging
from datetime import datetime, timedelta
from inspect import Signature
from itertools import count
from pathlib import Path
from tkinter import Label
from typing import Optional, Callable, Union

from PIL import Image
from PIL.ImageTk import PhotoImage
from PIL.Image import Image as PILImage
from PySimpleGUI import Image as ImageElement

from ds_tools.images.colors import color_at_pos
from ds_tools.images.animated.cycle import PhotoImageCycle
from ds_tools.images.animated.gif import AnimatedGif
from ds_tools.images.animated.spinner import Spinner
from ds_tools.images.lcd import SevenSegmentDisplay
from ds_tools.images.utils import ImageType, Size, as_image, calculate_resize

__all__ = ['ExtendedImage', 'Spacer', 'SpinnerImage', 'ClockImage']
log = logging.getLogger(__name__)


class ExtendedImage(ImageElement):
    def __init__(
        self,
        image: ImageType = None,
        popup_title: str = None,
        init_callback: Callable = None,
        bind_click: bool = True,
        click_image: ImageType = None,
        **kwargs
    ):
        self._bind_click = bind_click
        self.click_image = click_image
        self._image = None
        super().__init__(**kwargs)
        self.image = image
        self._popup_title = popup_title
        self._current_size = self._get_size(*self.Size)
        self._init_callback = init_callback
        self._animation = None  # type: Optional[Animation]
        self._current_image = None

    def __repr__(self):
        if (widget := self._widget) is not None:
            size = widget.winfo_width(), widget.winfo_height()
            pos = widget.winfo_x(), widget.winfo_y()
        else:
            size = self.Size
            pos = ('?', '?')
        return f'<{self.__class__.__qualname__}[key={self.Key!r}, {size=} {pos=}]>'

    @property
    def position(self):
        if (widget := self._widget) is not None:
            return widget.winfo_x(), widget.winfo_y()
        return None

    @property
    def animation(self) -> Optional['Animation']:
        return self._animation

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
    def image(self, data: Union[ImageType, tuple[ImageType, ImageType]]):
        if isinstance(data, tuple):
            data, self.click_image = data
        self._image = as_image(data)
        if self._widget is not None:
            self.resize(*self._current_size)

    @property
    def current_size(self):
        return self._current_size

    def resize(self, width: int, height: int):
        if image := self._image:
            new_w, new_h = self._get_size(width, height)
            # self.log.log(19, f'Resizing image from {img_w}x{img_h} to {new_w}x{new_h}')
            if image.format == 'GIF':
                n, paused = (a.frame_num, a.paused) if (a := self._animation) else (0, False)
                self._animation = Animation(self, self._widget, image, self._current_size, n, paused)
                self._animation.next(True)
            else:
                try:
                    self._current_image = resized = image.resize((new_w, new_h), Image.ANTIALIAS)
                    tk_image = PhotoImage(resized)
                except OSError as e:
                    log.warning(f'Error resizing {image}: {e}')
                else:
                    self._current_size = (new_w, new_h)
                    self._widget.configure(image=tk_image, width=new_w, height=new_h)
                    self._widget.image = tk_image
                    self._widget.pack(padx=self.pad_used[0], pady=self.pad_used[1])
            if self._bind_click:
                self._widget.bind('<Button-1>', self.handle_click)

    def _get_size(self, width: int, height: int):
        if (image := self._image) is not None:
            if width is None or height is None:
                img_w, img_h = image.size
                width = width if width is not None else img_w
                height = height if height is not None else img_h
            return calculate_resize(*image.size, width, height)
        return width, height

    def handle_click(self, event):
        from ..popups.image import ImageView

        ImageView(self.click_image or self._image, self._popup_title).get_result()

    def get_pixel_color(self, x: int, y: int, relative: bool = True) -> Union[tuple[int, ...], int]:
        if relative:  # X and Y are from a click Event
            img_x, img_y = self.position
            x -= img_x
            y -= img_y
        image = self._animation.current_image if self._animation else self._current_image
        return color_at_pos(image, (x, y))


class _AnimatedImage(ExtendedImage):
    @property
    def Widget(self) -> Optional[Label]:
        return self._widget

    @Widget.setter
    def Widget(self, tktext_label: Label):
        self._widget = tktext_label
        if tktext_label is not None:
            self.resize(*self.Size)
            if callback := self._init_callback:
                callback(self)

    def _get_size(self, width: int, height: int):
        try:
            old_w, old_h = self._current_size
        except AttributeError:
            return width, height
        return calculate_resize(old_w, old_h, width, height)


class SpinnerImage(_AnimatedImage):
    _spinner_keys = set(Signature.from_callable(Spinner).parameters.keys())

    def __init__(self, *args, bind_click: bool = False, **kwargs):
        spinner_kwargs = {key: kwargs.pop(key) for key in self._spinner_keys if key in kwargs}
        size = spinner_kwargs.setdefault('size', (200, 200))
        spinner_kwargs.setdefault('frame_fade_pct', 0.01)
        spinner_kwargs.setdefault('frame_duration_ms', 20)
        spinner_kwargs.setdefault('frames_per_spoke', 3)
        self._spinner = Spinner(**spinner_kwargs)
        super().__init__(*args, bind_click=bind_click, size=size, **kwargs)

    def resize(self, width: int, height: int):
        size = calculate_resize(*self._current_size, width, height)
        n, paused = (a.frame_num, a.paused) if (a := self._animation) else (0, False)
        self._animation = Animation(self, self._widget, self._spinner, size, n, paused)
        self._animation.next(True)
        if self._bind_click:
            self._widget.bind('<Button-1>', self.handle_click)


class ClockImage(_AnimatedImage):
    _clock_keys = set(Signature.from_callable(SevenSegmentDisplay).parameters.keys())

    def __init__(self, *args, slim: bool = False, **kwargs):
        self._slim = slim
        self._clock_kwargs = {key: kwargs.pop(key) for key in self._clock_keys if key in kwargs}
        self._clock_kwargs.setdefault('bar_pct', 0.2)
        self._include_seconds = kwargs.pop('seconds', True)
        self._clock = SevenSegmentDisplay(**self._clock_kwargs)
        kwargs.setdefault('size', self._clock.time_size(self._include_seconds))
        kwargs['bind_click'] = False
        kwargs.setdefault('background_color', 'black')
        kwargs.setdefault('pad', (0, 0))
        super().__init__(*args, **kwargs)

    def resize(self, width: int, height: int):
        width, height = size = calculate_resize(*self._current_size, width, height)
        if a := self._animation:
            a.resize(width, height)
        else:
            self._clock.resize(self._clock.calc_width(height))
            paused = False
            self._animation = ClockAnimation(
                self, self._widget, size, self._clock, self._include_seconds, paused, self._slim
            )
            self._animation.next()
            if self._bind_click:
                self._widget.bind('<Button-1>', self.handle_click)


class Animation:
    def __init__(
        self,
        image_ele: ExtendedImage,
        widget: Label,
        image: Union[PILImage, Spinner, Path, str],
        size: Size,
        last_frame_num: int = 0,
        paused: bool = False,
    ):
        self._image_ele = image_ele
        self._widget = widget
        self._size = size
        if isinstance(image, Spinner):
            self._frames = image.resize(size).cycle(PhotoImage)
        elif isinstance(image, (Path, str)):
            self._frames = PhotoImageCycle(Path(image).expanduser())
        else:  # TODO: PhotoImageCycle will not result in expected resize behavior...
            if path := getattr(image, 'filename', None) or getattr(getattr(image, 'fp', None), 'name', None):
                self._frames = PhotoImageCycle(Path(path))
            else:
                self._frames = AnimatedGif(image).resize(size, 1).cycle(PhotoImage)
        self._frames.n = last_frame_num
        log.debug(f'Prepared {len(self._frames)} frames')
        self._next_id = widget.after(self._frames.first_delay, self.next)
        self._run = not paused

    @property
    def current_image(self) -> PILImage:
        return self._frames.current_image

    @property
    def frame_num(self) -> int:
        return self._frames.n

    @property
    def paused(self):
        return not self._run

    def next(self, init: bool = False):
        frame, delay = next(self._frames)
        width, height = self._size
        self._widget.configure(image=frame, width=width, height=height)
        if init:
            self._widget.image = frame
            x, y = self._image_ele.pad_used
            self._widget.pack(padx=x, pady=y)
        if self._run:
            self._next_id = self._widget.after(delay, self.next)

    def previous(self):
        frame, delay = self._frames.back()
        width, height = self._size
        self._widget.configure(image=frame, width=width, height=height)
        if self._run:
            self._next_id = self._widget.after(delay, self.previous)

    def pause(self):
        self._run = False
        if self._next_id is not None:
            try:
                self._widget.after_cancel(self._next_id)
            except Exception as e:
                log.debug(f'Error canceling next animation step: {e}')
            self._next_id = None

    def resume(self):
        self._run = True
        self.next()


class ClockAnimation(Animation):
    def __init__(  # noqa
        self,
        image_ele: ExtendedImage,
        widget: Label,
        size: Size,
        lcd_clock: SevenSegmentDisplay,
        seconds: bool,
        paused: bool = False,
        slim: bool = False,
    ):
        self._image_ele = image_ele
        self._widget = widget
        self._size = size
        self._next_id = widget.after(0, self.next)
        self._run = not paused
        self.lcd_clock = lcd_clock
        self._seconds = seconds
        self._last_time = datetime.now() - timedelta(seconds=1)
        self._delay = 200 if seconds else 1000
        self._slim = slim

    def toggle_slim(self):
        lcd_clock = self.lcd_clock
        lcd_clock.resize(lcd_clock.width, bar_pct=(lcd_clock._bar_pct * 2 if self._slim else lcd_clock._bar_pct / 2))
        self._slim = not self._slim
        self._last_time = datetime.now() - timedelta(seconds=1)

    @property
    def frame_num(self) -> int:
        return 1

    def resize(self, width, height):
        self.lcd_clock.resize(self.lcd_clock.calc_width(height))
        self._size = (width, height)
        self._last_time = datetime.now() - timedelta(seconds=1)

    def next(self):  # noqa
        widget = self._widget
        now = datetime.now()
        if now - self._last_time >= timedelta(seconds=1):
            self._last_time = now
            image = PhotoImage(self.lcd_clock.draw_time(now, self._seconds))
            width, height = self._size
            widget.configure(image=image, width=width, height=height)
            widget.image = image
            x, y = self._image_ele.pad_used
            widget.pack(padx=x, pady=y)
        if self._run:
            self._next_id = widget.after(self._delay, self.next)

    previous = next


class Spacer(ImageElement):
    _count = count()

    def __init__(self, *args, key=None, **kwargs):
        key = key or f'spacer::{next(self._count)}'
        kwargs.setdefault('pad', (0, 0))
        super().__init__(*args, key=key, **kwargs)
