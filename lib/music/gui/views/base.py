"""
Gui Views

:author: Doug Skrypa
"""

import inspect
import logging
import webbrowser
from abc import ABC, abstractmethod
from copy import deepcopy
from pathlib import Path
from functools import partial, update_wrapper, cached_property
from typing import Any, Optional, Callable, Type, Mapping, Union, Collection

from PySimpleGUI import Window, WIN_CLOSED, Element, Text, OK, Menu, Column

from .exceptions import NoEventHandlerRegistered

__all__ = ['ViewManager', 'GuiView', 'BaseView', 'event_handler']
log = logging.getLogger(__name__)


class WindowLoopMixin(ABC):
    window: Optional[Window]

    @abstractmethod
    def handle_event(self, event: str, data: dict[str, Any]):
        return NotImplemented

    def __iter__(self):
        return self

    def __next__(self) -> tuple[str, dict[str, Any]]:
        event, data = self.window.read()
        if event == 'Exit' or event == WIN_CLOSED:
            raise StopIteration
        return event, data

    def run(self):
        for event, data in self:
            try:
                self.handle_event(event, data)
            except StopIteration:
                break

        self.window.close()


class ViewManager(WindowLoopMixin):
    def __init__(self, *args, **kwargs):
        self.window: Optional[Window] = None
        self._window_size = (None, None)
        self.args = args
        self.kwargs = kwargs
        self.view: Optional['GuiView'] = None

    @staticmethod
    def _new_window(layout: list[list[Element]], args, kwargs) -> Window:
        # noinspection PyTypeChecker
        new_window = Window(*args, layout=layout, **kwargs)
        new_window.finalize()
        # new_window.read(0)
        new_window.bind('<Configure>', 'config_changed')  # Capture window size change as an event
        return new_window

    def load(self, view: 'GuiView') -> Window:
        layout, kwargs = view.get_render_args()
        if view.primary:
            new_window = self._new_window(layout, self.args, deepcopy(self.kwargs) | kwargs)
            self.view = view
            if self.window is not None:
                self.window.close()
            self.window = new_window
            self._window_size = new_window.size
        else:
            kwargs.setdefault('keep_on_top', True)
            kwargs.setdefault('modal', True)
            new_window = self._new_window(layout, (), kwargs)
        return new_window

    def handle_event(self, event: str, data: dict[str, Any]):
        self.view.handle_event(event, data)

    def __call__(self, view_cls: Type['GuiView']):
        view_cls(self).render()
        self.run()


class event_handler:
    """
    Register the decorated method as an event handler.  Uses the name of the method as the name of the event.
    No arguments are required, and the decorator does not need to be called when using default options.

    To register event aliases as well, provide the names of the aliases as parameters for the decorator.  Due to the
    nature of the somewhat hacky way that __new__ is implemented to accomplish this behavior, IDEs may not understand
    why arguments are being passed to the decorator.
    """
    def __new__(
        cls, func: Union[Callable, str] = None, *args: str, aliases: Collection[str] = None, default: bool = False
    ):
        if isinstance(func, Callable):
            return super().__new__(cls)
        else:
            if isinstance(func, str):  # somewhat hacky
                aliases = (func, *args)
            return partial(cls, aliases=aliases, default=default)

    def __init__(self, func, aliases: Collection[str] = None, default: bool = False):
        self.aliases = aliases
        self.func = func
        self.default = default
        update_wrapper(self, func)

    def __set_name__(self, owner: Type['GuiView'], name: str):
        if handlers := owner._event_handlers:
            # print(f'{owner.__name__} already has handlers: {", ".join(sorted(handlers))}')
            if (handler_cls := next(iter(handlers.values()))[1]) is not owner:
                handler_cls.event_handlers = handler_cls.event_handlers.copy() | {k: v[0] for k, v in handlers.items()}
                handler_cls._event_handlers.clear()

        # print(f'Registering {owner.__name__}.{self.func.__name__} as handler={name!r}')
        owner._event_handlers[name] = self.func, owner
        if self.aliases:
            for alias in self.aliases:
                # print(f'Registering {owner.__name__}.{self.func.__name__} as handler={alias!r}')
                owner._event_handlers[alias] = self.func, owner

        if self.default:
            if (handler := getattr(owner, '_default_handler', None)) is not None:
                raise AssertionError(
                    f'Cannot register method={self.func.__name__!r} as the default handler for {owner.__name__} - it'
                    f' already has default_handler={handler.__name__!r}'
                )
            # print(f'Registering {owner.__name__}.{self.func.__name__} as the default handler for {owner.__name__}')
            owner._default_handler = self.func

        setattr(owner, name, self.func)  # replace wrapper with the original function


class GuiView(WindowLoopMixin, ABC):
    _views = {}
    _event_handlers = {}
    event_handlers = {}
    default_handler: Optional[Callable] = None
    name: str = None
    primary: bool

    # noinspection PyMethodOverriding
    def __init_subclass__(cls, view_name: str, primary: bool = True):
        cls._views[view_name] = cls
        cls.name = view_name
        cls.primary = primary
        cls.event_handlers = cls.event_handlers.copy() | {k: v[0] for k, v in cls._event_handlers.items()}
        cls._event_handlers.clear()
        cls.default_handler = getattr(cls, '_default_handler', None)
        if cls.default_handler is not None:
            del cls._default_handler  # noqa
        # print(f'Initialized subclass={cls.__name__!r}')

    def __init__(self, mgr: 'ViewManager', binds: Mapping[str, str] = None):
        self.mgr = mgr
        self.window: Optional[Window] = None
        self.binds = binds
        # log.debug(f'{self} initialized with handlers: {", ".join(sorted(self.event_handlers))}')

    def __repr__(self):
        return f'<{self.__class__.__name__}[{self.name}][{self.primary=!r}][handlers: {len(self.event_handlers)}]>'

    def _get_default_handler(self):
        for cls in self.__class__.mro():
            if (handler := getattr(cls, 'default_handler', None)) is not None:
                # log.debug(f'{self}: Found default_handler={handler.__name__}')
                return handler
        # log.debug(f'{self}: No default handler found')
        return None

    def handle_event(self, event: str, data: dict[str, Any]):
        try:
            handler = self.event_handlers[event]
        except KeyError:
            if (handler := self._get_default_handler()) is None:
                # for cls in self.__class__.mro():
                #     print(f'{cls.__name__}:')
                #     try:
                #         for handler in sorted(cls.event_handlers):  # noqa
                #             print(f'    - {handler}')
                #     except AttributeError:
                #         pass
                raise NoEventHandlerRegistered(self, event) from None

        if event != 'config_changed':
            log.debug(f'{self}: Handling {event=}')
        # log.debug(f'Calling {handler} with args=({self}, {event!r}, {data!r})')
        result = handler(self, event, data)
        if isinstance(result, GuiView):
            result.render()
            if not result.primary:
                log.debug(f'Waiting for {result}')
                result.run()
                log.debug(f'Finished {result}')

    @abstractmethod
    def get_render_args(self) -> tuple[list[list[Element]], dict[str, Any]]:
        return NotImplemented

    def render(self):
        # for cls in [GuiView, *GuiView.__subclasses__()]:
        #     print(f'{cls.__name__}:')
        #     for handler in sorted(cls.event_handlers):
        #         print(f'    - {handler}')
        self.window = self.mgr.load(self)
        if self.binds:
            for key, val in self.binds.items():
                self.window.bind(key, val)
        log.debug(f'Rendered {self}')

    @event_handler
    def config_changed(self, event: str, data: dict[str, Any]):
        """
        Event handler for window configuration changes.

        Known triggers:
            - Resize window
            - Move window
            - Window gains focus
            - Scroll

        """
        new_size = self.window.size
        old_size = self.mgr._window_size
        if old_size != new_size:
            self.mgr._window_size = new_size
            if handler := self.event_handlers.get('window_resized'):
                handler(self, event, {'old_size': old_size, 'new_size': new_size})  # original data is empty


class BaseView(GuiView, view_name='base'):
    def __init__(self, mgr: 'ViewManager'):
        super().__init__(mgr)
        self.menu = [
            ['File', ['Exit']],
            ['Help', ['About']],
        ]

    def get_render_args(self) -> tuple[list[list[Element]], dict[str, Any]]:
        return [[Menu(self.menu)]], {}

    def handle_event(self, event: str, data: dict[str, Any]):
        try:
            super().handle_event(event, data)
        except NoEventHandlerRegistered as e:
            if e.view is self:
                log.warning(e)
            else:
                raise

    @event_handler('About')  # noqa
    def about(self, event: str, data: dict[str, Any]):
        return AboutView(self.mgr)

    # @event_handler
    # def window_resized(self, event: str, data: dict[str, Any]):
    #     log.debug(f'Window size changed from {data["old_size"]} to {data["new_size"]}')
    #     if self.state.get('view') == 'tracks':
    #         log.debug(f'Expanding columns on {self.window}')
    #         expand_columns(self.window.Rows)


class AboutView(GuiView, view_name='about', primary=False):
    def __init__(self, mgr: 'ViewManager'):
        super().__init__(mgr, binds={'<Escape>': 'Exit'})

    @cached_property
    def top_level_name(self):
        try:
            return Path(inspect.getsourcefile(inspect.stack()[-1][0])).stem
        except Exception as e:
            log.debug(f'Error determining top-level script info: {e}')
            return '[unknown]'

    @cached_property
    def top_level_globals(self):
        try:
            return inspect.stack()[-1].frame.f_globals
        except Exception as e:
            log.debug(f'Error determining top-level script info: {e}')
            return {}

    @cached_property
    def url(self):
        return self.top_level_globals.get('__url__', '[unknown]')

    @event_handler
    def link_clicked(self, event: str, data: dict[str, Any]):
        webbrowser.open(self.url)

    @event_handler(default=True)  # noqa
    def default(self, event: str, data: dict[str, Any]):
        raise StopIteration

    def get_render_args(self) -> tuple[list[list[Element]], dict[str, Any]]:
        if self.url != '[unknown]':
            link = Text(self.url, enable_events=True, key='link_clicked', text_color='blue')
        else:
            link = Text(self.url)

        layout = [
            [Text('Program:', size=(12, 1)), Text(self.top_level_name)],
            [Text('Author:', size=(12, 1)), Text(self.top_level_globals.get('__author__', '[unknown]'))],
            [Text('Version:', size=(12, 1)), Text(self.top_level_globals.get('__version__', '[unknown]'))],
            [Text('Project URL:', size=(12, 1)), link],
            [OK()],
        ]
        return layout, {'title': 'About'}


def expand_columns(rows: list[list[Element]]):
    for row in rows:
        for ele in row:
            if isinstance(ele, Column):
                ele.expand(True, True)
            try:
                ele_rows = ele.Rows
            except AttributeError:
                pass
            else:
                log.debug(f'Expanding columns on {ele}')
                expand_columns(ele_rows)
