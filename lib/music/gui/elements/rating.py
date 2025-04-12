import logging
from functools import cached_property
from itertools import count
from typing import Optional, Literal, Iterator, Callable

from PIL.Image import Image as PILImage, new as new_image
from FreeSimpleGUI import Column, Text, Element, ELEM_TYPE_GRAPH

from ...common.ratings import star_fill_counts, stars_to_256
from ..icons import Icons
from .image import ExtendedImage
from .inputs import ExtInput

__all__ = ['Rating']
log = logging.getLogger(__name__)

Color = Literal['black', 'gold']
FillAmount = Literal['empty', 'full', 'half']


class Rating(Column):
    _count = count()

    def __init__(
        self,
        rating: int = None,
        color: Literal['mix', 'black', 'gold'] = 'mix',
        key: str = None,
        star_size: tuple[int, int] = None,
        show_value: bool = False,
        disabled: bool = False,
        tooltip: str = None,
        change_cb: Callable = None,
        **kwargs
    ):
        if color not in ('mix', 'black', 'gold'):
            raise ValueError(f'Invalid {color=} - only mix, black, and gold are supported')
        self.rating = rating or 0
        self._valid_value = 0 <= self.rating <= 10
        self._color = color
        self._key = key or f'rating::{next(self._count)}'
        width, height = self._star_size = star_size or (12, 12)
        self._star_full_size = (width * 5 + 4, height)
        self._show_value = show_value
        self._disabled = disabled
        self._tooltip = tooltip
        self._val_change_cb = None
        self._last_cb_rating = self.rating
        self._button_down = False
        self._change_cb = change_cb
        super().__init__(self.prepare_layout(), key=self._key, **kwargs)

    def __repr__(self):
        return f'<{self.__class__.__name__}({self.rating}, key={self._key!r}, {self._show_value=}, {self._disabled=})>'

    @cached_property
    def _star_images(self) -> dict[Color, dict[FillAmount, PILImage]]:
        colors = {'gold': '#F2D250', 'black': '#000000'}
        names = {'empty': 'star', 'half': 'star-half', 'full': 'star-fill'}
        icons = Icons(max(self._star_size))
        images = {
            color: {name: icons.draw(icon, color=rgb, bg='#ffffff00') for name, icon in names.items()}
            for color, rgb in colors.items()
        }
        return images

    def prepare_layout(self) -> list[list[Element]]:
        if rating_input := self.rating_input:
            return [[rating_input, Text('(out of 10)', size=(8, 1)), self.star_element]]
        else:
            return [[self.star_element]]

    def _make_key(self, *args):
        return '::'.join((f'_{self._key}', *args))

    @cached_property
    def rating_input(self) -> Optional[ExtInput]:
        if self._show_value:
            return ExtInput(
                self.rating, key=self._make_key('input'), disabled=self._disabled, size=(5, 1), tooltip=self._tooltip
            )
        return None

    @cached_property
    def star_element(self) -> ExtendedImage:
        return ExtendedImage(
            self._combined_stars(),
            key=self._make_key('stars'),
            size=self._star_full_size,
            pad=(0, 0),
            bind_click=False,
            init_callback=lambda i: self._finish_init(),
        )

    def _combined_stars(self) -> PILImage:
        width, height = self._star_size
        combined = new_image('RGBA', self._star_full_size)
        for i, image in enumerate(self._iter_star_images()):
            combined.paste(image, (width * i + i, 0))
        return combined

    def _iter_star_images(self) -> Iterator[PILImage]:
        rating = self.rating if self._valid_value else 0
        images = self._star_images[self._color if self._color != 'mix' else 'gold' if rating else 'black']
        for key, num in zip(('full', 'half', 'empty'), star_fill_counts(rating, half=True)):
            if num:
                image = images[key]  # noqa
                for _ in range(num):
                    yield image

    def _handle_star_clicked(self, event):
        self._button_down = True
        rating = round(int(100 * event.x / self.star_element.Widget.winfo_width()) / 10)
        self.rating = rating = 10 if rating > 10 else 0 if rating < 0 else rating
        if rating_input := self.rating_input:
            rating_input.update(rating)
            rating_input.validated(True)
        else:
            self.star_element.image = self._combined_stars()

    def _handle_value_changed(self, tk_var_name: str, index, operation: str):
        rating_input = self.rating_input
        if value := rating_input.TKStringVar.get():
            try:
                value = int(value)
                stars_to_256(value, 10)
            except (ValueError, TypeError) as e:
                from ..popups.text import popup_error

                self.validated(False)
                popup_error(f'Invalid rating:\n{e}', auto_size=True)
            else:
                self.validated(True)
        else:
            self.validated(True)
            value = 0

        self.rating = value
        self.star_element.image = self._combined_stars()
        self._maybe_callback()

    def validated(self, valid: bool):
        if self._valid_value != valid:
            self._valid_value = valid
        if rating_input := self.rating_input:
            rating_input.validated(valid)

    def _finish_init(self):
        self.Type = ELEM_TYPE_GRAPH  # Used to trick PySimpleGUI into returning a value for this element (1/2)
        if not self._disabled:
            self._disabled = True  # will be set back to False by .enable()
            self.enable()
        if (rating_input := self.rating_input) and not self._valid_value:
            rating_input.validated(False)

    def _handle_button_released(self, event):
        self._button_down = False
        self._maybe_callback()

    def _maybe_callback(self):
        if self._change_cb is not None and not self._button_down:
            if self._last_cb_rating != self.rating and self._valid_value:
                self._last_cb_rating = self.rating
                self._change_cb(self)

    def enable(self):
        if not self._disabled:
            return
        widget = self.star_element.Widget
        widget.bind('<Button-1>', self._handle_star_clicked)
        widget.bind('<ButtonRelease-1>', self._handle_button_released)
        widget.bind('<B1-Motion>', self._handle_star_clicked)
        if rating_input := self.rating_input:
            rating_input.update(disabled=False)
            self._val_change_cb = rating_input.TKStringVar.trace_add('write', self._handle_value_changed)
        self._disabled = False

    def disable(self):
        if self._disabled:
            return
        widget = self.star_element.Widget
        widget.unbind('<Button-1>')
        widget.unbind('<B1-Motion>')
        if rating_input := self.rating_input:
            rating_input.TKStringVar.trace_remove('write', self._val_change_cb)
            self._val_change_cb = None
            rating_input.update(disabled=True)
        self._disabled = True

    def update(self, rating: int = None, disabled: bool = None, **kwargs):
        if disabled:
            self.disable()
        elif disabled is False:
            self.enable()

        if rating is not None:
            if not (0 <= rating <= 10):
                raise ValueError(f'Invalid {rating=} - value must be between 0 and 10, inclusive')
            self.rating = rating
            self.star_element.image = self._combined_stars()

        super().update(**kwargs)

    @property
    def ClickPosition(self):  # Used to trick PySimpleGUI into returning a value for this element (2/2)
        return self.rating

    def bind(self, bind_string, key_modifier, propagate: bool = True):
        if rating_input := self.rating_input:
            rating_input.bind(bind_string, key_modifier, propagate=propagate)
        else:
            super().bind(bind_string, key_modifier, propagate=propagate)


if __name__ == '__main__':
    from ..popups.base import BasePopup
    from ds_tools.logging import init_logging

    init_logging(10, names=None, millis=True, set_levels={'PIL': 30})

    # BasePopup.test_popup([[Rating(i), Text(f'Rating: {i:>2d} {stars(i)}')] for i in range(11)])
    BasePopup.test_popup([[Rating(i, show_value=True, change_cb=print)] for i in range(11)])
    # BasePopup.test_popup([[Rating(i)] for i in range(11)])
