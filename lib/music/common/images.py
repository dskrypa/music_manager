"""
Utilities for working with images

:author: Doug Skrypa
"""

import logging
from io import BytesIO
from pathlib import Path
from typing import Union, Optional, Callable

from PIL import Image
from PIL.Image import Image as PILImage

__all__ = ['ImageType', 'as_image']
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



