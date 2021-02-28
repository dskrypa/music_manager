"""
Base GUI class that uses PySimpleGUI, but adds event handler registration via a decorator.

:author: Doug Skrypa
"""

import inspect
import logging
from abc import ABC
from contextlib import suppress
from copy import deepcopy
from functools import wraps
from pathlib import Path
from types import FunctionType
from typing import Callable, Dict, Tuple, Any, List, Optional

from PySimpleGUI import Window, WIN_CLOSED, Element, Text, OK

from .state import GuiState

__all__ = ['GuiBase', 'event_handler', 'view']
log = logging.getLogger(__name__)


class GuiBase(ABC):
    window: Optional[Window]

    def __init_subclass__(cls):
        cls._event_handlers = {}  # type: Dict[str, Callable]
        cls._views = {}
        for attr in dir(cls):
            with suppress(AttributeError):
                method = getattr(cls, attr)
                if isinstance(method, FunctionType):
                    with suppress(AttributeError):
                        for event in method.events:  # noqa
                            cls._event_handlers[event] = method
                    with suppress(AttributeError):
                        cls._views[method.view] = method  # noqa

    def __init__(self, *args, **kwargs):
        self.window = None
        self._window_args = args
        self._window_kwargs = kwargs
        self._window_size = (None, None)
        self.state = GuiState()

    def set_layout(self, layout: List[List[Element]], **kwargs):
        kw_args = deepcopy(self._window_kwargs)
        kw_args.update(kwargs)
        if self.window is not None:
            self.window.close()
        self.window = Window(*self._window_args, layout=layout, **kw_args)
        self.window.finalize()
        self.window.bind('<Configure>', '__CONFIG_CHANGED__')  # Capture window size change as an event
        self._window_size = self.window.size

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

    def show_view(self, name: str):
        try:
            handler = self._views[name]
        except KeyError:
            log.error(f'Invalid view={name!r}')
        else:
            handler(self)

    def _config_changed(self, event: str, data: Dict[str, Any]):
        """
        Event handler for window configuration changes.

        Known triggers:
            - Resize window
            - Move window
            - Window gains focus
            - Scroll

        """
        new_size = self.window.size
        old_size = self._window_size
        if old_size != new_size:
            self._window_size = new_size
            if handler := self._event_handlers.get('window_resized'):
                handler(self, event, {'old_size': old_size, 'new_size': new_size})  # original data is empty

    # noinspection PyMethodMayBeStatic
    def about(self, event: str, data: Dict[str, Any]):
        try:
            top_level_frame_info = inspect.stack()[-1]
            top_level_name = Path(inspect.getsourcefile(top_level_frame_info[0])).stem
            top_level_globals = top_level_frame_info.frame.f_globals
        except Exception as e:
            log.debug(f'Error determining top-level script info: {e}')
            top_level_name = '[unknown]'
            top_level_globals = {}

        layout = [
            [Text('Program:', size=(12, 1)), Text(top_level_name)],
            [Text('Author:', size=(12, 1)), Text(top_level_globals.get('__author__', '[unknown]'))],
            [Text('Version:', size=(12, 1)), Text(top_level_globals.get('__version__', '[unknown]'))],
            [Text('Project URL:', size=(12, 1)), Text(top_level_globals.get('__url__', '[unknown]'))],
            [OK()],
        ]

        window = Window('About', layout=layout)
        window.finalize()
        window.bind('<Escape>', 'Exit')
        window.read()
        window.close()


def event_handler(*event: str):
    def _event_handler(func):
        func.events = event
        return func

    return _event_handler


def view(name: str):
    def _view(func):
        func.view = name

        @wraps(func)
        def show_view(self, *args, **kwargs):
            result = func(self, *args, **kwargs)
            self.state['view'] = name
            return result

        return show_view

    return _view


event_handler('__CONFIG_CHANGED__')(GuiBase._config_changed)  # noqa
event_handler('About')(GuiBase.about)  # noqa
