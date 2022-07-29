"""
Utilities for generating PIL images based on `Bootstrap <https://icons.getbootstrap.com/>`_ icons, using the
bootstrap-icons font.

:author: Doug Skrypa
"""

from __future__ import annotations

from base64 import b64encode
from io import BytesIO
from math import floor, ceil
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Union, Callable

from PIL.Image import Image as PILImage, new as new_image, open as open_image
from PIL.ImageDraw import ImageDraw, Draw
from PIL.ImageFont import FreeTypeFont, truetype
from PIL.JpegImagePlugin import RAWMODE

from .color import Color, color_to_rgb

if TYPE_CHECKING:
    from .typing import XY, ImageType

__all__ = ['Icons', 'image_path', 'as_image', 'image_to_bytes', 'scale_image', 'calculate_resize']

ICONS_DIR = Path(__file__).resolve().parents[3].joinpath('icons')
ICON_DIR = ICONS_DIR.joinpath('bootstrap')
Icon = Union[str, int]


def image_path(rel_path: str) -> Path:
    return ICONS_DIR.joinpath(rel_path)


class Icons:
    __slots__ = ('font',)
    _font: Optional[FreeTypeFont] = None
    _names: Optional[dict[str, int]] = None

    def __init__(self, size: int = 10):
        if self._font is None:
            self.__class__._font = truetype(ICON_DIR.joinpath('bootstrap-icons.woff').as_posix())
        self.font: FreeTypeFont = self._font.font_variant(size=size)

    @property
    def char_names(self) -> dict[str, int]:
        if self._names is None:
            import json

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

    def draw(self, icon: Icon, size: XY = None, color: Color = '#000000', bg: Color = '#ffffff') -> PILImage:
        icon = self._normalize(icon)
        if size:
            font = self.font.font_variant(size=max(size))
        else:
            font = self.font
            size = (font.size, font.size)

        image = new_image('RGBA', size, color_to_rgb(bg))
        draw = Draw(image)  # type: ImageDraw
        draw.text((0, 0), icon, fill=color_to_rgb(color), font=font)
        return image

    def draw_base64(self, *args, **kwargs) -> bytes:
        bio = BytesIO()
        self.draw(*args, **kwargs).save(bio, 'PNG')
        return b64encode(bio.getvalue())


def as_image(image: ImageType) -> PILImage:
    if image is None or isinstance(image, PILImage):
        return image
    elif isinstance(image, bytes):
        return open_image(BytesIO(image))
    elif isinstance(image, (Path, str)):
        path = Path(image).expanduser()
        if not path.is_file():
            raise ValueError(f'Invalid image path={path.as_posix()!r} - it is not a file')
        return open_image(path)
    else:
        raise TypeError(f'Image must be bytes, None, Path, str, or a PIL.Image.Image - found {type(image)}')


def image_to_bytes(image: ImageType, format: str = None, size: XY = None, **kwargs) -> bytes:  # noqa
    image = as_image(image)
    if size:
        image = scale_image(image, *size, **kwargs)
    if not (save_fmt := format or image.format):
        save_fmt = 'png' if image.mode == 'RGBA' else 'jpeg'
    if save_fmt == 'jpeg' and image.mode not in RAWMODE:
        image = image.convert('RGB')

    bio = BytesIO()
    image.save(bio, save_fmt)
    return bio.getvalue()


# region Image Resizing


def scale_image(image: PILImage, width: float, height: float, **kwargs) -> PILImage:
    new_size = calculate_resize(*image.size, width, height)
    return image.resize(new_size, **kwargs)


def calculate_resize(src_w: float, src_h: float, new_w: float, new_h: float) -> tuple[float, float]:
    """Copied logic from :meth:`PIL.Image.Image.thumbnail`"""
    x, y = floor(new_w), floor(new_h)
    aspect = src_w / src_h
    if x / y >= aspect:
        x = _round_aspect(y * aspect, key=lambda n: abs(aspect - n / y))
    else:
        y = _round_aspect(x / aspect, key=lambda n: 0 if n == 0 else abs(aspect - x / n))
    return x, y


def _round_aspect(number: float, key: Callable[[float], float]) -> float:
    rounded = min(floor(number), ceil(number), key=key)
    return rounded if rounded > 1 else 1


# endregion
