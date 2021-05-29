"""
Progress indicator helpers

:author: Doug Skrypa
"""

import logging
from pathlib import Path
from typing import Union, TypeVar, Iterable, Iterator

from PySimpleGUI import popup_animated, ProgressBar

from ..files.track.track import SongFile

__all__ = ['Spinner', 'ProgressTracker']
SPINNERS_DIR = Path(__file__).resolve().parents[3].joinpath('icons', 'spinners')
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
        # TODO: Remove the constants file with base64 gifs
        self.image_source = image_source or SPINNERS_DIR.joinpath('blue_dots_noalpha.gif')
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
        popup_animated(self.image_source, *self.args, **self.kwargs)

    def close(self):  # noqa
        popup_animated(None)


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
