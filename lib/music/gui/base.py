"""
Base GUI class that uses PySimpleGUI, but adds event handler registration via a decorator.

:author: Doug Skrypa
"""

import logging
from abc import ABC
from contextlib import suppress
from copy import deepcopy
from types import FunctionType
from typing import Callable, Dict, Tuple, Any, List, Optional

from PySimpleGUI import Window, WIN_CLOSED, Element

__all__ = ['GuiBase', 'event_handler']
log = logging.getLogger(__name__)


class GuiBase(ABC):
    window: Optional[Window]

    def __init_subclass__(cls):
        cls._event_handlers = {}  # type: Dict[str, Callable]
        for attr in dir(cls):
            with suppress(AttributeError):
                method = getattr(cls, attr)
                if isinstance(method, FunctionType):
                    for event in method.events:  # noqa
                        cls._event_handlers[event] = method

    def __init__(self, *args, **kwargs):
        self.window = None
        self._window_args = args
        self._window_kwargs = kwargs

    def set_layout(self, layout: List[List[Element]], **kwargs):
        kw_args = deepcopy(self._window_kwargs)
        kw_args.update(kwargs)
        if self.window is not None:
            self.window.close()
        self.window = Window(*self._window_args, layout=layout, **kw_args)

    def __iter__(self):
        return self

    def __next__(self) -> Tuple[str, Dict[str, Any]]:
        event, data = self.window.read()
        if event == 'Exit' or event == WIN_CLOSED:
            raise StopIteration
        return event, data

    def run(self):
        for event, data in self:
            try:
                handler = self._event_handlers[event]
            except KeyError:
                log.warning(f'No handler for {event=}')
            else:
                log.debug(f'Handling {event=}')
                handler(self, event, data)

        self.window.close()


def event_handler(*event: str):
    def _event_handler(func):
        func.events = event
        return func

    return _event_handler
