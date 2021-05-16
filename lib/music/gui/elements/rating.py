"""
Rating element for PySimpleGui

:author: Doug Skrypa
"""

import logging
from itertools import count
from pathlib import Path
from tkinter import Label
from typing import Union, Optional, Literal, Iterator

from PIL import Image as ImageModule
from PIL.Image import Image as PILImage
from PySimpleGUI import Image, Column, Text

from ds_tools.core.decorate import cached_classproperty
from ...common.ratings import star_fill_counts
from .image import ExtendedImage

__all__ = ['Rating']
log = logging.getLogger(__name__)
ICONS_DIR = Path(__file__).resolve().parents[4].joinpath('icons')
Colors = Literal['mix', 'black', 'gold']


class Rating(Column):
    _count = count()

    def __init__(
        self, rating: int = None, color: Colors = 'mix', key: str = None, star_size: tuple[int, int] = None, **kwargs
    ):
        self.rating = rating or 0
        if color not in ('mix', 'black', 'gold'):
            raise ValueError(f'Invalid {color=} - only mix, black, and gold are supported')
        self._color = color
        self._key = key or f'rating::{next(self._count)}'
        self.star_size = star_size or (12, 12)
        super().__init__([self.star_elements], **kwargs)

    @cached_classproperty
    def star_images(cls) -> dict[Literal['black', 'gold'], dict[Literal['empty', 'full', 'half'], PILImage]]:  # noqa
        star_images = {'black': {}, 'gold': {}}
        for path in ICONS_DIR.glob('star-*.png'):
            fill, color = path.stem.split('-')[1:]
            star_images[color][fill] = ImageModule.open(path)
        return star_images  # noqa

    @property
    def star_elements(self) -> list[ExtendedImage]:
        kwargs = {'pad': (0, 0), 'size': self.star_size, '_in_popup': True}
        key_fmt = f'{self._key}::star::{{}}'.format
        return [ExtendedImage(img, key=key_fmt(i), **kwargs) for i, img in enumerate(self._star_images())]

    def _star_images(self) -> Iterator[PILImage]:
        images = self.star_images[self._color if self._color != 'mix' else 'gold' if self.rating else 'black']
        for key, num in zip(('full', 'half', 'empty'), star_fill_counts(self.rating, half=True)):
            if num:
                image = images[key]
                for _ in range(num):
                    yield image


if __name__ == '__main__':
    from ..popups.base import BasePopup
    from ...common.ratings import stars

    BasePopup.test_popup([[Rating(i), Text(f'Rating: {i:>2d} {stars(i)}')] for i in range(11)])
