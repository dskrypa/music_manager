"""
:author: Doug Skrypa
"""

import logging
from io import BytesIO
from typing import Union, Container

from PIL.Image import Image as PILImage, Resampling, MIME, open as open_image
from PIL.JpegImagePlugin import RAWMODE

__all__ = ['prepare_cover_image', 'bytes_to_image']
log = logging.getLogger(__name__)


def prepare_cover_image(
    image: PILImage, tag_types: Union[str, Container[str]], max_width: int = 1200
) -> tuple[PILImage, bytes, str]:
    if isinstance(tag_types, str):
        tag_types = {tag_types}

    save_fmt = image.format  # Needs to be stored before resize
    if image.width > max_width:
        width, height = image.size
        new_height = int(round(max_width * height / width))
        log.log(19, f'Resizing image from {width}x{height} to {max_width}x{new_height}')
        if image.mode == 'P':
            # In this case, Image.resize ignores the resample arg and uses Resampling.NEAREST, so convert to RGB first
            image = image.convert('RGB')
        image = image.resize((max_width, new_height), Resampling.LANCZOS)

    mime_type = MIME[save_fmt]
    if 'mp4' in tag_types and mime_type not in ('image/jpeg', 'image/png'):
        if image.mode not in RAWMODE:
            image = image.convert('RGB')
        mime_type = 'image/jpeg'
        save_fmt = 'jpeg'

    bio = BytesIO()
    log.debug(f'Saving {image=} to BytesIO object with {save_fmt=} {mime_type=}')
    image.save(bio, save_fmt)
    data = bio.getvalue()
    return image, data, mime_type


def bytes_to_image(data: bytes) -> PILImage:
    return open_image(BytesIO(data))
