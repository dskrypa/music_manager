"""
View: Show Image

:author: Doug Skrypa
"""

import math
from io import BytesIO
from typing import TYPE_CHECKING, Any, Union

from PySimpleGUI import Element, Image

from ..base import event_handler, GuiView

if TYPE_CHECKING:
    from PIL.Image import Image as PILImage

__all__ = ['ImageView']


class ImageView(GuiView, view_name='show_image', primary=False):
    def __init__(self, image: Union[Image, 'PILImage'], title: str = None, img_key: str = None):
        super().__init__(binds={'<Escape>': 'Exit'})
        self.title = title or 'Image'
        self.img_key = img_key or f'img::{id(image)}'
        self.gui_img = image
        self.pil_img = None if isinstance(image, Image) else image

    @property
    def gui_img(self):
        return self._gui_img

    @gui_img.setter
    def gui_img(self, image: Union[Image, 'PILImage']):
        if isinstance(image, Image):
            self._gui_img = image
        else:
            self._gui_img = Image(data=image_to_bytes(image), size=image.size, key=f'img::{id(image)}', pad=(2, 2))

    @event_handler(default=True)  # noqa
    def default(self, event: str, data: dict[str, Any]):
        raise StopIteration

    @event_handler
    def window_resized(self, event: str, data: dict[str, Any]):
        if self.pil_img is None:
            return
        new_w, new_h = data['new_size']
        new_w, new_h = calculate_resize(self.pil_img.size, (new_w - 4, new_h - 4))
        # self.log.log(19, f'Resizing image from {img_w}x{img_h} to {new_w}x{new_h}')
        image = self.pil_img.resize((new_w, new_h))
        self.gui_img.update(data=image_to_bytes(image), size=image.size)

    def get_render_args(self) -> tuple[list[list[Element]], dict[str, Any]]:
        layout = [[self.gui_img]]

        # width, height = img_size = self.image.Size
        # window_size = (width + 10, height + 10)
        # self.log.debug(f'Showing image with {img_size=} in window with {window_size=}')
        kwargs = {'title': self.title, 'resizable': True, 'element_justification': 'center', 'margins': (0, 0)}
        return layout, kwargs


def image_to_bytes(image: 'PILImage') -> bytes:
    bio = BytesIO()
    image.save(bio, format='PNG')
    return bio.getvalue()


def calculate_resize(src_size, new_size):
    """Copied logic from :meth:`PIL.Image.Image.thumbnail`"""
    x, y = map(math.floor, new_size)
    src_w, src_h = src_size
    aspect = src_w / src_h
    if x / y >= aspect:
        x = round_aspect(y * aspect, key=lambda n: abs(aspect - n / y))
    else:
        y = round_aspect(x / aspect, key=lambda n: 0 if n == 0 else abs(aspect - x / n))
    return x, y


def round_aspect(number, key):
    return max(min(math.floor(number), math.ceil(number), key=key), 1)
