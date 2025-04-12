"""
Progress indicator helpers

:author: Doug Skrypa
"""

import logging
from functools import cached_property
from typing import Union, TypeVar, Iterable, Iterator, Optional

from .elements.image import SpinnerImage, ExtendedImage
from .elements.text import ExtText
from .positioning import positioner
from .window import Window

__all__ = ['Spinner']
log = logging.getLogger(__name__)
T = TypeVar('T')


class Spinner:
    """
    Helper class for simplifying / automating spinner animations via :func:`<FreeSimpleGUI.popup_animated>`.
    Can be used as a context manager so that the animation is automatically ended at the end of the context block.  Can
    additionally be called to wrap an iterable (used similarly as the builtin :func:`enumerate` function) to
    automatically advance the animation on each iteration.
    """

    def __init__(self, image_source: Union[str, bytes] = None, *args, **kwargs):
        image = ExtendedImage(image_source, bind_click=False) if image_source is not None else None
        self._popup = SpinnerPopup(image, *args, **kwargs)
        self.update()

    def __enter__(self):
        self.update()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __call__(self, iterable: Iterable[T]) -> Iterator[T]:
        for item in iterable:
            self.update()
            yield item

    def update(self):
        self._popup.read()

    def close(self):  # noqa
        self._popup.close()


class SpinnerPopup:
    def __init__(
        self,
        image: ExtendedImage = None,
        message: str = None,
        *,
        size: tuple[int, int] = None,
        bg: str = None,
        fg: str = None,
        font=None,
        no_titlebar: bool = True,
        grab_anywhere: bool = True,
        keep_on_top: bool = True,
        location=(None, None),
        alpha_channel=None,
        transparent_color=None,
        title: str = '',
        icon=None,
        parent: Window = None,
        **kwargs,
    ):
        size = size or (200, 200)
        self.image = image or SpinnerImage(size=size, background_color=bg, **kwargs)
        self._message = message
        self.text = ExtText(message, background_color=bg, text_color=fg, font=font)
        self._parent = parent
        self.kwargs = dict(
            no_titlebar=no_titlebar,
            grab_anywhere=grab_anywhere,
            keep_on_top=keep_on_top,
            background_color=bg,
            location=location,
            alpha_channel=alpha_channel,
            element_padding=(0, 0),
            margins=(0, 0),
            transparent_color=transparent_color,
            element_justification='c',
            icon=icon,
            title=title,
        )

    def _find_parent(self) -> Optional[Window]:
        if self._parent:
            return self._parent
        from .base_view import GuiView
        return getattr(GuiView.active_view, 'window', None)

    @cached_property
    def window(self):
        layout = [[self.image], [self.text]] if self._message else [[self.image]]
        window = Window(layout=layout, finalize=True, **self.kwargs)
        window.read(1)
        if (parent := self._find_parent()) and not isinstance(parent, Window):
            parent = getattr(parent, 'window', None)
        pos = positioner.get_center(window, parent)
        window.move(*pos)
        return window

    def close(self):
        self.window.close()

    def read(self, timeout: int = 1):
        return self.window.read(timeout)
