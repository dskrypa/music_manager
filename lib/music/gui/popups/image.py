"""
View: Show Image

:author: Doug Skrypa
"""

import sys
from typing import Union

from PIL.Image import MIME
from FreeSimpleGUI import Image as GuiImage

from ds_tools.images.utils import ImageType, as_image
from ..elements.image import ExtendedImage
from ..base_view import event_handler, Event, EventData, RenderArgs
from ..positioning import positioner
from .base import BasePopup

__all__ = ['ImageView']


class ImageView(BasePopup, view_name='show_image', primary=False):
    def __init__(self, image: Union[GuiImage, ImageType], title: str = None, img_key: str = None):
        self.pil_img = image = as_image(image.Data if isinstance(image, GuiImage) else image)
        super().__init__(binds={'<Escape>': 'Exit'})
        self._title = title or 'Image'
        self.img_key = img_key or f'img::{id(image)}'
        if image:
            self.log.debug(f'Displaying {image=} with {image.format=} mime={MIME.get(image.format)!r}')
        self.orig_size = image.size if image else (0, 0)
        self._last_size = init_size = self._init_size()
        self.gui_img = ExtendedImage(image, size=init_size, key=self.img_key, pad=(2, 2), bind_click=False)

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
        px, py = self.gui_img.Pad
        target_w = new_w - (px * 2)
        target_h = new_h - (py * 2)
        # self.log.debug(f'{last_w=} {last_h=}  |  {target_w=} {target_h=}')
        if not ((last_h == new_h and target_w < new_w) or (last_w == new_w and target_h < new_h)):
            return target_w, target_h
        return None

    @event_handler
    def window_resized(self, event: Event, data: EventData):
        size = data['new_size']
        # if self.pil_img is None or self._last_size == size or monotonic() - self._last_resize < 0.15:
        if self.pil_img is None or self._last_size == size:
            # self.log.debug(f'Refusing resize too soon after last one')
            return
        elif new_size := self._get_new_size(*size):
            self._last_size = size
            self.gui_img.resize(*new_size)
            self.window.set_title(self.title)
            # self._last_resize = monotonic()

    def get_render_args(self) -> RenderArgs:
        layout = [[self.gui_img]]
        # TODO: Make large images scrollable instead of always shrinking the image; allow zoom without window resize
        kwargs = {'title': self.title, 'resizable': True, 'element_justification': 'center', 'margins': (0, 0)}
        return layout, kwargs


if __name__ == '__main__':
    from argparse import ArgumentParser
    parser = ArgumentParser()
    parser.add_argument('image_path', nargs='*', help='Path to an image file')
    args = parser.parse_args()
    if args.image_path:
        from ds_tools.logging import init_logging
        init_logging(12, log_path=None, names=None)
        try:
            ImageView(args.image_path[0]).get_result()
        except Exception as e:
            print(e, file=sys.stderr)
