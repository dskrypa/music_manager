"""
:author: Doug Skrypa
"""

import logging
from io import BytesIO
from typing import Union, Container

from PIL import Image

__all__ = ['prepare_cover_image']
log = logging.getLogger(__name__)


def prepare_cover_image(
    image: Image.Image, tag_types: Union[str, Container[str]], max_width: int = 1200
) -> tuple[Image.Image, bytes, str]:
    if isinstance(tag_types, str):
        tag_types = {tag_types}

    save_fmt = image.format  # Needs to be stored before resize
    if image.width > max_width:
        width, height = image.size
        new_height = int(round(max_width * height / width))
        log.log(19, f'Resizing image from {width}x{height} to {max_width}x{new_height}')
        image = image.resize((max_width, new_height))

    mime_type = Image.MIME[save_fmt]
    if 'mp4' in tag_types and mime_type not in ('image/jpeg', 'image/png'):
        if image.mode == 'RGBA':
            image = image.convert('RGB')
        mime_type = 'image/jpeg'
        save_fmt = 'jpeg'

    bio = BytesIO()
    log.debug(f'Saving {image=} to BytesIO object with {save_fmt=} {mime_type=}')
    image.save(bio, save_fmt)
    data = bio.getvalue()
    return image, data, mime_type
