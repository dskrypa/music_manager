"""
The base class for GUI views, and associated helpers.

Due to the relative immutability of PySimpleGUI Windows / their contents, each :class:`GuiView` is tied to a single
Window object.

Events (button clicks, form submission, etc) generated by a given :class:`GuiView` must be handled by that view.  View
methods may be registered as event handlers via the :class:`event_handler` decorator.  Each view is allowed to have one
default handler if necessary, and default handlers will be inherited from parent view classes.  A given event handler
method may handle multiple events by registering additional event strings with the decorator.

If an event handler returns a :class:`GuiView` object, then the view from which it was returned will be closed, and
focus will switch to the new view.

To start a program with a view, the :meth:`GuiView.start` classmethod should be called on the view class that defines
the main primary entry point / window.  It will run an event handler loop that always uses the active primary view's
event loop/handler.  If a non-primary view (for a temporary popup / prompt) is returned by an event handler, then
event handler loop control is transferred to that view until it is closed, and then the normal behavior is restored.

:author: Doug Skrypa
"""

from abc import ABC, abstractmethod
from copy import deepcopy
from functools import partial, update_wrapper
from typing import Any, Optional, Callable, Type, Mapping, Union, Collection

from PySimpleGUI import Window, WIN_CLOSED, Element, Menu

from .exceptions import NoEventHandlerRegistered
from .utils import ViewLoggerAdapter

__all__ = ['GuiView', 'BaseView', 'event_handler']
Layout = list[list[Element]]


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
            if isinstance(func, str):  # somewhat hacky, but it works to simplify arg handling
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


class GuiView(ABC):
    active_view: Optional['GuiView'] = None
    window: Optional[Window] = None
    _window_size: tuple[Optional[int], Optional[int]] = (None, None)  # width, height
    _primary_kwargs = {}
    _event_handlers = {}
    event_handlers = {}
    default_handler: Optional[Callable] = None
    name: str = None
    primary: bool

    # noinspection PyMethodOverriding
    def __init_subclass__(cls, view_name: str, primary: bool = True):
        cls.name = view_name
        cls.log = ViewLoggerAdapter(cls)
        cls.primary = primary
        cls.event_handlers = cls.event_handlers.copy() | {k: v[0] for k, v in cls._event_handlers.items()}
        cls._event_handlers.clear()
        cls.default_handler = getattr(cls, '_default_handler', None)
        if cls.default_handler is not None:
            del cls._default_handler  # noqa
        # print(f'Initialized subclass={cls.__name__!r}')

    def __init__(self, binds: Mapping[str, str] = None):
        self.binds = binds
        # self.log.debug(f'{self} initialized with handlers: {", ".join(sorted(self.event_handlers))}')

    def __repr__(self):
        return f'<{self.__class__.__name__}[{self.name}][{self.primary=!r}][handlers: {len(self.event_handlers)}]>'

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

    @classmethod
    def start(cls, **kwargs):
        if cls.active_view is not None:
            raise RuntimeError(f'{cls.active_view!r} is already active - only one view may be active at a time')
        cls._primary_kwargs.update(kwargs)
        if size := kwargs.get('size'):
            cls._window_size = size
        cls().render()

        while True:
            try:
                event, data = next(cls.active_view)  # noqa
                cls.active_view.handle_event(event, data)  # noqa
            except StopIteration:
                break

        cls.window.close()

    def _get_default_handler(self):
        for cls in self.__class__.mro():
            if (handler := getattr(cls, 'default_handler', None)) is not None:
                return handler
        return None

    def _handle_event(self, event: str, data: dict[str, Any]):
        try:
            handler = self.event_handlers[event]
        except KeyError:
            if (handler := self._get_default_handler()) is None:
                raise NoEventHandlerRegistered(self, event) from None

        if event != 'config_changed':
            self.log.debug(f'Handling {event=}')
        # self.log.debug(f'Calling {handler} with args=({self}, {event!r}, {data!r})')
        result = handler(self, event, data)
        if isinstance(result, GuiView):
            # self.log.debug(f'{self}: {event=!r} returned view={result!r} - rendering it')
            result.render()
            if not result.primary:
                self.log.debug(f'Waiting for {result}')
                result.run()
                self.log.debug(f'Finished {result}')
        # else:
        #     self.log.debug(f'{self}: {event=!r} returned {result=!r}')

    handle_event = _handle_event  # make original more easily accessible to descendent classes

    @abstractmethod
    def get_render_args(self) -> tuple[Layout, dict[str, Any]]:
        return NotImplemented

    def _create_window(self, layout: Layout, kwargs: dict[str, Any]) -> Window:
        # self.log.debug('Creating window')
        old_window = None if (last_view := GuiView.active_view) is None else last_view.window

        if self.primary:
            base_kwargs = deepcopy(self._primary_kwargs)
            if old_window is not None:
                base_kwargs['size'] = old_window.size
                base_kwargs['location'] = old_window.current_location()

            # self.log.debug(f'Base kwargs={base_kwargs}')
            kwargs = base_kwargs | kwargs
        else:
            kwargs.setdefault('keep_on_top', True)
            kwargs.setdefault('modal', True)

        kwargs.setdefault('margins', (5, 5))
        new_window = Window(
            layout=layout,
            finalize=True,
            **kwargs
        )
        new_window.bind('<Configure>', 'config_changed')  # Capture window size change as an event

        if self.primary:
            if old_window is not None:
                old_window.close()

            self.log.debug(f'Replacing GuiView.active_view={last_view.name if last_view else last_view}')
            GuiView.active_view = self

        return new_window

    def render(self):
        layout, kwargs = self.get_render_args()
        loc = self.__class__ if self.primary else self
        loc.window = self._create_window(layout, kwargs)
        loc._window_size = self.window.size
        if self.binds:
            for key, val in self.binds.items():
                self.window.bind(key, val)
        self.log.debug(f'Rendered {self}')

    @event_handler
    def config_changed(self, event: str, data: dict[str, Any]):
        """
        Event handler for window configuration changes.
        Known triggers: resize window, move window, window gains focus, scroll
        """
        loc = self.__class__ if self.primary else self
        new_size = loc.window.size
        old_size = loc._window_size
        if old_size != new_size:
            # self.log.debug(f'Window size changed: {old_size} -> {new_size}')
            loc._window_size = new_size
            if handler := self.event_handlers.get('window_resized'):
                handler(self, event, {'old_size': old_size, 'new_size': new_size})  # original data is empty


class BaseView(GuiView, view_name='base'):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.menu = [
            ['File', ['Exit']],
            ['Help', ['About']],
        ]

    def get_render_args(self) -> tuple[Layout, dict[str, Any]]:
        return [[Menu(self.menu)]], {}

    def handle_event(self, event: str, data: dict[str, Any]):
        try:
            return super().handle_event(event, data)
        except NoEventHandlerRegistered:
            # self.log.debug(f'No handler found for case-sensitive {event=!r} - will try again with snake_case version')
            pass
        try:
            return super().handle_event(event.lower().replace(' ', '_'), data)
        except NoEventHandlerRegistered as e:
            if e.view is self:
                self.log.warning(e)
            else:
                raise

    @event_handler
    def about(self, event: str, data: dict[str, Any]):
        from .popups.about import AboutView

        return AboutView()

    # @event_handler
    # def window_resized(self, event: str, data: dict[str, Any]):
    #     self.log.debug(f'Window size changed from {data["old_size"]} to {data["new_size"]}')
    #     if self.state.get('view') == 'tracks':
    #         self.log.debug(f'Expanding columns on {self.window}')
    #         expand_columns(self.window.Rows)
