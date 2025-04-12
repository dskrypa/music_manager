"""
View: Choose image from list

:author: Doug Skrypa
"""

from io import BytesIO
from textwrap import wrap
from typing import Any, Union, Optional

import PIL
from PIL.Image import Image as PILImage
from FreeSimpleGUI import Element, Button, Radio, Column, Image

from ..base_view import event_handler, Event, EventData
from .base import BasePopup
from .image import ImageView

__all__ = ['ChooseImagePopup', 'choose_image']


class ChooseImagePopup(BasePopup, view_name='choose_image_popup', primary=False):
    def __init__(
        self,
        images: dict[str, Union[bytes, PILImage]],
        title: str = '',
        img_size: tuple[int, int] = (250, 250),
        **kwargs
    ):
        super().__init__(binds={'<Escape>': 'Exit'}, title=title or 'Select an image')
        self.images = {
            title: PIL.Image.open(BytesIO(image)) if not isinstance(image, PILImage) else image
            for title, image in images.items()
        }
        self.expand_on_resize = ['col::choices']
        kwargs.setdefault('resizable', True)
        self.kwargs = kwargs
        self.img_size = img_size
        self._selected: bool = False

    @event_handler(default=True)
    def default(self, event: Union[str, tuple[str, int]], data: dict[str, Any]):
        if isinstance(event, tuple) and event[0] == 'choice':
            self.window['submit'].update(disabled=False)
            self.result = event[1]
        else:
            raise StopIteration

    def get_render_args(self) -> tuple[list[list[Element]], dict[str, Any]]:
        choices = []
        for title, image in self.images.items():  # type: str, PILImage
            try:
                image = image.copy()
                image.thumbnail(self.img_size)
            except Exception:
                self.log.error(f'Unable to render image={title!r}:', exc_info=True)
                data = None
            else:
                bio = BytesIO()
                image.save(bio, format='PNG')
                data = bio.getvalue()

            button_text = '\n'.join(wrap(title, break_long_words=False, break_on_hyphens=False, tabsize=4, width=30))
            choices.append([
                Radio(button_text, 'rad::choices', key=('choice', title), enable_events=True),
                Image(data=data, key=f'img::{title}', enable_events=True, size=self.img_size)
            ])

        images_shown = max(1, min(self.window.get_screen_size()[1] // 270, len(self.images)))
        content_col = Column(
            choices, key='col::choices', scrollable=True, vertical_scroll_only=True, size=(500, images_shown * 270)
        )
        layout = [[content_col, Button('Submit', key='submit', disabled=True)]]
        return layout, {'title': self.title, **self.kwargs}

    @event_handler('img::*')
    def image_clicked(self, event: Event, data: EventData):
        title = event.split('::', 1)[1]
        image = self.images[title]
        return ImageView(image, f'Album Cover: {title}')

    @event_handler
    def submit(self, event: str, data: dict[str, Any]):
        self._selected = True
        raise StopIteration

    def _get_result(self):
        self.render()
        self.run()
        return self.result if self._selected else None

    @event_handler
    def window_resized(self, event: Event, data: EventData):
        # data = {'old_size': old_size, 'new_size': new_size}
        key_dict = self.window.key_dict
        for key in self.expand_on_resize:
            if column := key_dict.get(key):
                # self.log.debug(f'Expanding {column=}')
                column.expand(True, True)


def choose_image(images: dict[str, Union[bytes, PILImage]], **kwargs) -> Optional[str]:
    if len(images) == 1:
        return next(iter(images))
    return ChooseImagePopup(images, **kwargs).get_result()
