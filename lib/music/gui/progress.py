"""
Progress indicator helpers

:author: Doug Skrypa
"""

import logging
from functools import cached_property
from typing import Union, TypeVar, Iterable, Iterator

from PySimpleGUI import popup_animated, ProgressBar, Window

from ..files.track.track import SongFile
from .elements.image import SpinnerImage
from .elements.text import ExtText

__all__ = ['Spinner', 'ProgressTracker']
# SPINNERS_DIR = Path(__file__).resolve().parents[3].joinpath('icons', 'spinners')
log = logging.getLogger(__name__)
T = TypeVar('T')


class Spinner:
    """
    Helper class for simplifying / automating spinner animations via :func:`popup_animated<PySimpleGUI.popup_animated>`.
    Can be used as a context manager so that the animation is automatically ended at the end of the context block.  Can
    additionally be called to wrap an iterable (used similarly as the builtin :func:`enumerate` function) to
    automatically advance the animation on each iteration.
    """

    def __init__(self, image_source: Union[str, bytes] = None, *args, **kwargs):
        self.image_source = image_source
        if image_source is None:
            kwargs.setdefault('size', (200, 200))
            self._popup = SpinnerPopup(**kwargs)
        else:
            self._popup = None
        self.args = args
        self.kwargs = kwargs
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
        if self._popup:
            self._popup.read()
        else:
            popup_animated(self.image_source, *self.args, **self.kwargs)

    def close(self):  # noqa
        if self._popup:
            self._popup.close()
        else:
            popup_animated(None)


class SpinnerPopup:
    def __init__(
        self,
        size: tuple[int, int],
        message: str = None,
        *,
        bg: str = None,
        fg: str = None,
        font=None,
        no_titlebar: bool = True,
        grab_anywhere: bool = True,
        keep_on_top: bool = True,
        location=(None, None),  # TODO: Auto-center
        alpha_channel=None,
        transparent_color=None,
        title: str = '',
        icon=None,
        **kwargs,
    ):
        self.image = SpinnerImage(size=size, background_color=bg, **kwargs)
        self._message = message
        self.text = ExtText(message, background_color=bg, text_color=fg, font=font)
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

    @cached_property
    def window(self):
        layout = [[self.image], [self.text]] if self._message else [[self.image]]
        return Window(layout=layout, finalize=True, **self.kwargs)

    def close(self):
        self.window.close()

    def read(self, timeout: int = 1):
        return self.window.read(timeout)


class ProgressTracker:
    def __init__(self, *args, text=None, **kwargs):
        self.bar = ProgressBar(*args, **kwargs)
        self.text = text
        self.complete = 0

    def update(self, text: Union[str, SongFile] = None, n: int = None):
        if text is not None:
            self.text.update(text.path.as_posix() if isinstance(text, SongFile) else text)
        self.complete += 1
        self.bar.update(self.complete)

    def __call__(self, iterable):
        for item in iterable:
            self.update()
            yield item


if __name__ == '__main__':
    import time
    from ds_tools.logging import init_logging
    init_logging(12, log_path=None, names=None)
    try:
        popup = SpinnerPopup((200, 200))
        while True:
            popup.read(0)

    except Exception as e:
        import sys
        print(e, file=sys.stderr)
