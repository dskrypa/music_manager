"""
Extended image elements for PySimpleGUI

:author: Doug Skrypa
"""

import logging
from itertools import count
from tkinter import Label
from typing import Optional, Callable, Union

from PIL import Image
from PIL.ImageTk import PhotoImage
from PIL.Image import Image as PILImage
from PySimpleGUI import Image as ImageElement

from ds_tools.images.colors import color_at_pos
from ds_tools.images.animated.gif import AnimatedGif
from ds_tools.images.utils import ImageType, as_image, calculate_resize

__all__ = ['ExtendedImage', 'Spacer']
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
                if image.format == 'GIF':
                    n, paused = (a.frame_num, a.paused) if (a := self._animation) else (0, False)
                    self._animation = Animation(self._widget, image, self._current_size, n, paused)

    def _get_size(self, width: int, height: int):
        if (image := self._image) is not None:
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


class Animation:
    def __init__(
        self, widget: Label, image: PILImage, size: tuple[int, int], last_frame_num: int = 0, paused: bool = False
    ):
        # TODO: Support ds_tools.images.animated.spinner.Spinner
        self._widget = widget
        self._size = size
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

    def next(self):
        frame, delay = next(self._frames)
        width, height = self._size
        self._widget.configure(image=frame, width=width, height=height)
        # self._widget.image = frame
        # self._widget.pack(padx=self.pad_used[0], pady=self.pad_used[1])
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


class Spacer(ImageElement):
    _count = count()

    def __init__(self, *args, key=None, **kwargs):
        key = key or f'spacer::{next(self._count)}'
        kwargs.setdefault('pad', (0, 0))
        super().__init__(*args, key=key, **kwargs)
