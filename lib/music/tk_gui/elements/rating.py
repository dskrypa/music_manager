"""
Tkinter GUI Rating Element

:author: Doug Skrypa
"""

from __future__ import annotations

import logging
from functools import cached_property
from tkinter import Event
from typing import TYPE_CHECKING, Optional, Iterator, Callable, Literal

from PIL.Image import Image as PILImage, new as new_image

from ...common.ratings import star_fill_counts, stars_to_256
from .frame import InteractiveRowFrame
from .images import Image
from .inputs import Input
from .text import Text

if TYPE_CHECKING:
    from ..typing import Bool, XY
    from .element import Element

__all__ = ['Rating']
log = logging.getLogger(__name__)

Color = Literal['black', 'gold']
RatingColor = Literal['black', 'gold', 'mix']
FillAmount = Literal['empty', 'full', 'half']


class Rating(InteractiveRowFrame):
    def __init__(
        self,
        rating: int = None,
        color: RatingColor = 'mix',
        star_size: XY = None,
        show_value: Bool = False,
        change_cb: Callable = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._rating = rating or 0
        self._valid_value = 0 <= self._rating <= 10
        self._color = color
        width, height = self._star_size = star_size or (12, 12)
        self._star_full_size = (width * 5 + 4, height)
        self._show_value = show_value
        self._val_change_cb = None
        self._last_cb_rating = self._rating
        self._button_down = False
        self._change_cb = change_cb

    def __repr__(self):
        return f'<{self.__class__.__name__}({self.rating}, key={self._key!r}, {self._show_value=}, {self.disabled=})>'

    # @property
    # def is_valid(self) -> bool:
    #     return 0 <= self._rating <= 10

    @property
    def value(self) -> int:
        return self.rating

    @property
    def rating(self) -> int:
        # return self._rating if self.is_valid else 0
        return self._rating if self._valid_value else 0

    @rating.setter
    def rating(self, value: int):
        self._rating = 10 if value > 10 else 0 if value < 0 else value

    @property
    def color(self) -> Color:
        if (color := self._color) != 'mix':
            return color
        return 'gold' if self.rating else 'black'  # noqa

    @cached_property
    def _star_images(self) -> dict[Color, dict[FillAmount, PILImage]]:
        from ..icons import Icons

        colors = {'gold': '#F2D250', 'black': '#000000'}
        names = {'empty': 'star', 'half': 'star-half', 'full': 'star-fill'}
        icons = Icons(max(self._star_size))
        images = {
            color: {name: icons.draw(icon, color=rgb, bg='#ffffff00') for name, icon in names.items()}
            for color, rgb in colors.items()
        }
        return images

    def _combined_stars(self) -> PILImage:
        width, height = self._star_size
        combined = new_image('RGBA', self._star_full_size)
        for i, image in enumerate(self._iter_star_images()):
            combined.paste(image, (width * i + i, 0))
        return combined

    def _iter_star_images(self) -> Iterator[PILImage]:
        images = self._star_images[self.color]
        for key, num in zip(('full', 'half', 'empty'), star_fill_counts(self.rating, half=True)):
            if num:
                image = images[key]  # noqa
                for _ in range(num):
                    yield image

    @cached_property
    def rating_input(self) -> Optional[Input]:
        if not self._show_value:
            return None
        return Input(self._rating, disabled=self.disabled, size=(5, 1), tooltip=self.tooltip_text)

    @cached_property
    def star_element(self) -> Image:
        return Image(self._combined_stars(), size=self._star_full_size, pad=(0, 0))

    @property
    def elements(self) -> tuple[Element, ...]:
        if rating_input := self.rating_input:
            return rating_input, Text('(out of 10)', size=(8, 1)), self.star_element
        return (self.star_element,)  # noqa

    def pack_elements(self, debug: Bool = False):
        super().pack_elements(debug)
        if not self.disabled:
            self.disabled = True    # Due to the `if not self.disabled` check
            self.enable()           # Apply binds and maybe add the input var trace
        if (rating_input := self.rating_input) and not self._valid_value:
            rating_input.validated(False)

    def _handle_star_clicked(self, event: Event):
        self._button_down = True
        self.rating = round(int(100 * event.x / self.star_element.widget.winfo_width()) / 10)
        if rating_input := self.rating_input:
            rating_input.update(self.rating)
            rating_input.validated(True)
            # The rating input value change will trigger _handle_value_changed to update the star element
        else:
            self.star_element.image = self._combined_stars()

    def _handle_value_changed(self, tk_var_name: str, index, operation: str):
        rating_input = self.rating_input
        if value := rating_input.value:
            try:
                value = int(value)
                stars_to_256(value, 10)
            except (ValueError, TypeError) as e:
                log.warning(f'Invalid rating: {e}')
                # TODO: error popup
                self.validated(False)
                # popup_error(f'Invalid rating:\n{e}', auto_size=True)
            else:
                self.validated(True)
        else:
            self.validated(True)
            value = 0

        self._rating = value
        self.star_element.image = self._combined_stars()
        self._maybe_callback()

    def validated(self, valid: bool):
        if self._valid_value != valid:
            self._valid_value = valid
        if rating_input := self.rating_input:
            rating_input.validated(valid)

    def _handle_button_released(self, event):
        self._button_down = False
        self._maybe_callback()

    def _maybe_callback(self):
        if self._change_cb is not None and not self._button_down:
            if self._last_cb_rating != self._rating and self._valid_value:
                self._last_cb_rating = self._rating
                self._change_cb(self)

    def update(self, rating: int = None, disabled: Bool = None):
        if disabled is not None:
            if disabled:
                self.disable()
            else:
                self.enable()
        if rating is not None:
            if not (0 <= rating <= 10):
                raise ValueError(f'Invalid {rating=} - value must be between 0 and 10, inclusive')
            self._rating = rating
            self.star_element.image = self._combined_stars()

    def enable(self):
        if not self.disabled:
            return
        widget = self.star_element.widget
        widget.bind('<Button-1>', self._handle_star_clicked)
        widget.bind('<ButtonRelease-1>', self._handle_button_released)
        widget.bind('<B1-Motion>', self._handle_star_clicked)
        if rating_input := self.rating_input:
            rating_input.enable()
            self._val_change_cb = rating_input.string_var.trace_add('write', self._handle_value_changed)
        self.disabled = False

    def disable(self):
        if self.disabled:
            return
        widget = self.star_element.widget
        widget.unbind('<Button-1>')
        widget.unbind('<B1-Motion>')
        if rating_input := self.rating_input:
            rating_input.string_var.trace_remove('write', self._val_change_cb)
            self._val_change_cb = None
            rating_input.disable()
        self.disabled = True
