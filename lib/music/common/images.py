"""
Utilities for working with images

:author: Doug Skrypa
"""

import logging
from io import BytesIO
from math import floor, ceil
from pathlib import Path
from typing import Union

from PIL import Image
from PIL.Image import Image as PILImage

__all__ = ['ImageType', 'as_image', 'image_to_bytes', 'calculate_resize', 'scale_image']
log = logging.getLogger(__name__)
ImageType = Union[PILImage, bytes, Path, str, None]


def as_image(image: ImageType) -> PILImage:
    if image is None or isinstance(image, PILImage):
        return image
    elif isinstance(image, bytes):
        return Image.open(BytesIO(image))
    elif isinstance(image, (Path, str)):
        return Image.open(image)
    else:
        raise TypeError(f'Image must be bytes, None, Path, str, or a PIL.Image.Image - found {type(image)}')


def image_to_bytes(image: ImageType, format: str = None, size: tuple[int, int] = None, **kwargs) -> bytes:  # noqa
    image = as_image(image)
    if size:
        image = scale_image(image, *size, **kwargs)
    if not (save_fmt := format or image.format):
        save_fmt = 'png' if image.mode == 'RGBA' else 'jpeg'
    if save_fmt == 'jpeg' and image.mode == 'RGBA':
        image = image.convert('RGB')

    bio = BytesIO()
    image.save(bio, save_fmt)
    return bio.getvalue()


def scale_image(image: PILImage, width, height, **kwargs) -> PILImage:
    new_size = calculate_resize(*image.size, width, height)
    return image.resize(new_size, **kwargs)


def calculate_resize(src_w, src_h, new_w, new_h):
    """Copied logic from :meth:`PIL.Image.Image.thumbnail`"""
    x, y = map(floor, (new_w, new_h))
    aspect = src_w / src_h
    if x / y >= aspect:
        x = _round_aspect(y * aspect, key=lambda n: abs(aspect - n / y))
    else:
        y = _round_aspect(x / aspect, key=lambda n: 0 if n == 0 else abs(aspect - x / n))
    return x, y


def _round_aspect(number, key):
    return max(min(floor(number), ceil(number), key=key), 1)
