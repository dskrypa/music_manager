"""
View: Show Image

:author: Doug Skrypa
"""

import sys
from math import ceil
from time import monotonic
from typing import Union

from PIL import Image
from PySimpleGUI import Image as GuiImage, Button, Column

from ds_tools.images.utils import ImageType, as_image
from ..elements.image import ExtendedImage, ClockImage
from ..elements.text import ExtText
from ..base_view import event_handler, Event, EventData, RenderArgs
from ..positioning import positioner
from .base import BasePopup

__all__ = ['ImageView', 'ClockView']


class ImageView(BasePopup, view_name='show_image', primary=False):
    def __init__(self, image: Union[GuiImage, ImageType], title: str = None, img_key: str = None):
        self.pil_img = image = as_image(image.Data if isinstance(image, GuiImage) else image)
        super().__init__(binds={'<Escape>': 'Exit'})
        self._title = title or 'Image'
        self.img_key = img_key or f'img::{id(image)}'
        if image:
            self.log.debug(f'Displaying {image=} with {image.format=} mime={Image.MIME.get(image.format)!r}')
        self.orig_size = image.size if image else (0, 0)
        self._last_size = init_size = self._init_size()
        self.gui_img = ExtendedImage(image, size=init_size, key=self.img_key, pad=(2, 2), bind_click=False)
        self._last_resize = 0

    def _init_size(self):
        monitor = positioner.get_monitor_for_window(self.window)
        img_w, img_h = self.orig_size
        return min(monitor.width - 70, img_w or 0), min(monitor.height - 70, img_h or 0)

    @property
    def title(self):
        try:
            img_w, img_h = self.gui_img.current_size
        except TypeError:
            return self._title
        else:
            src_w, src_h = self.orig_size
            return f'{self._title} ({img_w}x{img_h}, {img_w / src_w if src_w else 1:.0%})'

    @title.setter
    def title(self, value):
        self._title = value

    def _get_new_size(self, new_w: int, new_h: int):
        last_w, last_h = self._last_size
        target_w = new_w - 4
        target_h = new_h - 6
        # self.log.debug(f'{last_w=} {last_h=}  |  {target_w=} {target_h=}')
        if not ((last_h == new_h and target_w < new_w) or (last_w == new_w and target_h < new_h)):
            return target_w, target_h
        return None

    @event_handler
    def window_resized(self, event: Event, data: EventData):
        if self.pil_img is None:
            return
        elif monotonic() - self._last_resize < 0.1:
            # self.log.debug(f'Refusing resize too soon after last one')
            return
        elif new_size := self._get_new_size(*data['new_size']):
            # self.log.debug(f'Resizing image from {self._last_size} to {new_size}')
            self._last_size = new_size
            self.gui_img.resize(*new_size)
            self.window.set_title(self.title)
            self._last_resize = monotonic()

    def get_render_args(self) -> RenderArgs:
        layout = [[self.gui_img]]
        # TODO: Make large images scrollable instead of always shrinking the image; allow zoom without window resize
        kwargs = {'title': self.title, 'resizable': True, 'element_justification': 'center', 'margins': (0, 0)}
        return layout, kwargs


class ClockView(ImageView, view_name='clock_view', primary=False):
    def __init__(self, *args, width: int = 40, seconds: bool = True, slim: bool = False, **kwargs):
        super().__init__(None, *args, **kwargs)
        self.gui_img = ClockImage(width=width, seconds=seconds, slim=slim)
        self.orig_size = self._last_size = self.gui_img.Size
        self._show_titlebar = False

    @event_handler
    def window_resized(self, event: Event, data: EventData):
        if monotonic() - self._last_resize < 0.1:
            return
        elif new_size := self._get_new_size(*data['new_size']):
            self._last_size = new_size
            self.gui_img.resize(*new_size)
            self.window.set_title(self.title)
            self._last_resize = monotonic()

    def get_render_args(self) -> RenderArgs:
        layout = [[self.gui_img]]
        kwargs = {
            'title': self.title,
            'resizable': True,
            'element_justification': 'center',
            'margins': (0, 0),
            'border_depth': 0,
            'background_color': 'black',
            'alpha_channel': 0.8,
            'grab_anywhere': True,
            'no_titlebar': True,
        }
        return layout, kwargs

    def increase_size(self, event):
        width, height = self.window.size
        height += 10
        clock = self.gui_img._clock
        new_width, _height = clock.time_size(self.gui_img._show_seconds, clock.calc_width(height))
        width = max(width, new_width)
        self.window.size = (width, height)

    def decrease_size(self, event):
        width, height = self.window.size
        height -= 10
        clock = self.gui_img._clock
        new_width, _height = clock.time_size(self.gui_img._show_seconds, clock.calc_width(height))
        if (ceil(clock.bar_pct * clock.calc_width(_height - 6)) if clock.bar_pct else clock.bar) < 3:
            self.log.debug('Unable to decrease clock size further')
            return
        width = min(width, new_width)
        self.window.size = (width, height)

    def show_hide_title(self, event):
        self.window.TKroot.wm_overrideredirect(self._show_titlebar)
        self._show_titlebar = not self._show_titlebar

    def toggle_slim(self, event):
        self.gui_img.toggle_slim()

    def post_render(self):
        super().post_render()
        widget = self.gui_img._widget
        widget.bind('<Button-2>', self.toggle_slim)  # Middle click
        widget.bind('<Button-3>', self.show_hide_title)  # Right click
        bind = self.window.TKroot.bind
        bind('<KeyPress-plus>', self.increase_size)
        bind('<KeyPress-minus>', self.decrease_size)


class ImageView2(ImageView, view_name='show_image_2', primary=False):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._paused = False
        self._prev = Button('Previous', disabled=True)
        self._next = Button('Next', disabled=True)
        self._toggle = Button('Pause', key='play_pause')
        self._frame_n = ExtText('', key='frame_num', visible=False, size=(3, 1))

    @event_handler(default=True)
    def default(self, event: Event, data: EventData):
        pass
        # self.log.debug(f'Received unhandled {event=}')

    def _get_new_size(self, new_w: int, new_h: int):
        last_w, last_h = self._last_size
        target_w = new_w - 4
        target_h = new_h - 6 - 60
        # self.log.debug(f'{last_w=} {last_h=}  |  {target_w=} {target_h=}')
        if not ((last_h == new_h and target_w < new_w) or (last_w == new_w and target_h < new_h)):
            return target_w, target_h
        return None

    def get_render_args(self) -> RenderArgs:
        layout = [
            [self.gui_img],
            [Column([[ExtText(''), self._frame_n, ExtText('')]])],
            [self._prev, self._toggle, self._next],
        ]
        kwargs = {'title': self.title, 'resizable': True, 'element_justification': 'center', 'margins': (0, 0)}
        return layout, kwargs

    def post_render(self):
        super().post_render()
        self.gui_img._widget.bind('<Button-1>', self.handle_click)

    @event_handler
    def play_pause(self, event: Event, data: EventData):
        self._paused = paused = not self._paused
        if paused:
            self.gui_img.animation.pause()
        else:
            self.gui_img.animation.resume()
        self._prev.update(disabled=not paused)
        self._next.update(disabled=not paused)
        self._frame_n.update(self.gui_img.animation.frame_num, visible=paused)
        self._toggle.update('Play' if paused else 'Pause')

    @event_handler('Previous')
    def previous(self, event: Event, data: EventData):
        self.log.info(f'Rewinding...')
        self.gui_img.animation.previous()
        self._frame_n.update(self.gui_img.animation.frame_num)

    @event_handler('Next')
    def next(self, event: Event, data: EventData):
        self.log.info(f'Stepping forward...')
        self.gui_img.animation.next()
        self._frame_n.update(self.gui_img.animation.frame_num)

    def handle_click(self, event):
        pos = (event.x, event.y)
        color = self.gui_img.get_pixel_color(*pos)
        hex_color = ''.join(map('{:02X}'.format, color[:3]))
        self.log.info(f'Click {pos=} {color=} hex_color=#{hex_color}')


if __name__ == '__main__':
    from argparse import ArgumentParser
    parser = ArgumentParser()
    parser.add_argument('image_path', nargs='*', help='Path to an image file')
    args = parser.parse_args()
    if args.image_path:
        from ds_tools.logging import init_logging
        init_logging(12, log_path=None, names=None)
        try:
            ClockView().get_result()
            # ImageView2(args.image_path[0]).get_result()
        except Exception as e:
            print(e, file=sys.stderr)
