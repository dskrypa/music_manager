"""
Utilities for generating PIL images based on `Bootstrap <https://icons.getbootstrap.com/>`_ icons, using the
bootstrap-icons font.

:author: Doug Skrypa
"""

from __future__ import annotations

import json
import logging
from base64 import b64encode
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Union

from PIL import Image
from PIL.ImageDraw import ImageDraw, Draw
from PIL.ImageFont import FreeTypeFont, truetype

from ds_tools.images.colors import Color, color_to_rgb

if TYPE_CHECKING:
    from PIL.Image import Image as PILImage
    from ds_tools.images.utils import Size

__all__ = ['Icons']
log = logging.getLogger(__name__)

ICON_DIR = Path(__file__).resolve().parents[3].joinpath('icons', 'bootstrap')
Icon = Union[str, int]


class Icons:
    _font: Optional[FreeTypeFont] = None
    _names: Optional[dict[str, int]] = None

    def __init__(self, size: int = 10):
        if self._font is None:
            self.__class__._font = truetype(ICON_DIR.joinpath('bootstrap-icons.woff').as_posix())
        self.font: FreeTypeFont = self._font.font_variant(size=size)

    @property
    def char_names(self):
        if self._names is None:
            with ICON_DIR.joinpath('bootstrap-icons.json').open('r', encoding='utf-8') as f:
                self.__class__._names = json.load(f)
        return self._names

    def change_size(self, size: int):
        self.font = self.font.font_variant(size=size)

    def __getitem__(self, char_name: str) -> str:
        return chr(self.char_names[char_name])

    def _normalize(self, icon: Icon) -> str:
        if isinstance(icon, int):
            return chr(icon)
        try:
            return self[icon]
        except KeyError:
            return icon

    def draw(self, icon: Icon, size: Size = None, color: Color = '#000000', bg: Color = '#ffffff') -> PILImage:
        icon = self._normalize(icon)
        if size:
            font = self.font.font_variant(size=max(size))
        else:
            font = self.font
            size = (font.size, font.size)

        image = Image.new('RGBA', size, color_to_rgb(bg))
        draw = Draw(image)  # type: ImageDraw
        draw.text((0, 0), icon, fill=color_to_rgb(color), font=font)
        return image

    def draw_base64(self, *args, **kwargs) -> bytes:
        bio = BytesIO()
        image = self.draw(*args, **kwargs)
        image.save(bio, 'PNG')
        return b64encode(bio.getvalue())
