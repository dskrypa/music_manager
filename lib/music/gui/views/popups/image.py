"""
View: Show Image

:author: Doug Skrypa
"""

from io import BytesIO
from typing import Any, Union

from PIL import Image
from PySimpleGUI import Element, Image as GuiImage

from ...elements.image import ExtendedImage
from ..base import event_handler
from .base import BasePopup

__all__ = ['ImageView']


class ImageView(BasePopup, view_name='show_image', primary=False):
    def __init__(self, image: Union[GuiImage, Image.Image], title: str = None, img_key: str = None):
        super().__init__(binds={'<Escape>': 'Exit'})
        self._title = title or 'Image'
        self.img_key = img_key or f'img::{id(image)}'
        if isinstance(image, GuiImage):
            image = Image.open(BytesIO(image.Data))
        self.pil_img = image
        self.orig_size = image.size
        self.gui_img = ExtendedImage(image=image, size=self._init_size(), key=self.img_key, pad=(2, 2))
        self._last_size = None

    def _init_size(self):
        dsp_w, dsp_h = self.window.get_screen_size()
        img_w, img_h = self.orig_size
        return min(dsp_w - 70, img_w or 0), min(dsp_h - 70, img_h or 0)

    @property
    def title(self):
        try:
            img_w, img_h = self.gui_img._real_size
        except TypeError:
            return self._title
        else:
            src_w, src_h = self.orig_size
            return f'{self._title} ({img_w}x{img_h}, {img_w / src_w:.0%})'

    @title.setter
    def title(self, value):
        self._title = value

    @event_handler
    def window_resized(self, event: str, data: dict[str, Any]):
        if self.pil_img is None:
            return
        new_w, new_h = data['new_size']
        try:
            last_w, last_h = self._last_size
        except TypeError:
            self.gui_img.resize(new_w - 4, new_h - 4)
            self.window.set_title(self.title)
        else:
            target_w = new_w - 4
            target_h = new_h - 4
            if not ((last_h == new_h and target_w < new_w) or (last_w == new_w and target_h < new_h)):
                self.gui_img.resize(new_w - 4, new_h - 4)
                self.window.set_title(self.title)

    def get_render_args(self) -> tuple[list[list[Element]], dict[str, Any]]:
        layout = [[self.gui_img]]
        # TODO: Make large images scrollable instead of always shrinking the image; allow zoom without window resize
        kwargs = {'title': self.title, 'resizable': True, 'element_justification': 'center', 'margins': (0, 0)}
        return layout, kwargs
