"""
The base class for GUI views, and associated helpers.

Due to the relative immutability of PySimpleGUI Windows / their contents, each :class:`GuiView` is tied to a single
Window object.

Events (button clicks, form submission, etc) generated by a given :class:`GuiView` must be handled by that view.  View
methods may be registered as event handlers via the :func:`event_handler` decorator.  Each view is allowed to have one
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

import re
from abc import ABC, abstractmethod
from copy import deepcopy
from fnmatch import _compile_pattern
from functools import partial, update_wrapper
from itertools import count
from queue import Queue, Empty
from threading import Thread
from typing import TYPE_CHECKING, Any, Optional, Callable, Type, Mapping, Collection, Union

from PySimpleGUI import Window, WIN_CLOSED, Element, theme
from screeninfo import get_monitors, Monitor

from .config import GuiConfig
from .constants import LoadingSpinner
from .exceptions import NoEventHandlerRegistered, MonitorDetectionError
from .progress import Spinner
from .utils import ViewLoggerAdapter

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ['GuiView', 'event_handler', 'Event', 'EventData', 'EleBinds', 'RenderArgs']
Layout = list[list[Element]]
Event = Union[str, tuple]
EventData = dict[Union[str, int, tuple], Any]
Kwargs = dict[str, Any]
EleBinds = dict[str, dict[str, Event]]
RenderArgs = Union[Layout, tuple[Layout, Kwargs], tuple[Layout, Kwargs, EleBinds]]

DEFAULT_SETTINGS = {'remember_pos': True, 'theme': 'DarkGrey10'}


def event_handler(*args, **kwargs):
    """
    Register the decorated method as an event handler.  Uses the name of the method as the name of the event.
    No arguments are required, and the decorator does not need to be called when using default options.

    Aliases may be registered as positional args to the decorator.
    """
    if not args:
        return partial(_EventHandler, **kwargs)
    elif isinstance(args[0], str):
        return partial(_EventHandler, aliases=args, **kwargs)
    return _EventHandler(*args, **kwargs)


class _EventHandler:
    """Not intended to be used directly - use :func:`event_handler` instead"""
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
    primary: bool
    name: str = None
    permissive_handler_names: bool = True
    allow_no_handler: bool = True
    active_view: Optional['GuiView'] = None
    window: Optional[Window] = None
    pending_prompts = Queue()
    config = GuiConfig(auto_save=True, defaults=DEFAULT_SETTINGS)
    default_handler: Optional[Callable] = None
    wildcard_handlers: dict[str, dict[Callable, Callable]] = {}
    event_handlers = {}
    _event_handlers = {}
    _primary_kwargs = {}
    _counter = count()
    _ele_event_match = re.compile(r'^(.*?):::([a-zA-Z_]+)$').match
    _window_size: tuple[Optional[int], Optional[int]] = (None, None)  # width, height
    _window_pos: tuple[Optional[int], Optional[int]] = (None, None)  # x, y
    _monitors = get_monitors()

    # noinspection PyMethodOverriding
    def __init_subclass__(
        cls,
        view_name: str,
        primary: bool = True,
        defaults: Mapping[str, Any] = None,
        permissive_handler_names: bool = None,
        allow_no_handler: bool = None,
        config_path: Union[str, 'Path'] = None,
    ):
        cls.name = view_name
        cls.log = ViewLoggerAdapter(cls)
        cls.primary = primary
        cls.event_handlers = cls.event_handlers.copy() | {k: v[0] for k, v in cls._event_handlers.items()}
        cls._event_handlers.clear()
        cls.default_handler = getattr(cls, '_default_handler', None)
        if cls.default_handler is not None:
            del cls._default_handler  # noqa
        if config_path:  # The latest class to set this wins - does not support multiple paths within the same run
            cls.config.path = config_path
        if defaults:
            cls.config.defaults.update(defaults)
        if permissive_handler_names is not None:
            cls.permissive_handler_names = permissive_handler_names
        if allow_no_handler is not None:
            cls.allow_no_handler = allow_no_handler
        # print(f'Initialized subclass={cls.__name__!r}')

    def __init__(self, binds: Mapping[str, str] = None):
        self.parent: Optional[GuiView] = None if self.primary else GuiView.active_view
        self._monitor = None
        self._view_num = next(self._counter)
        self.binds = binds or {}
        # self.log.debug(f'{self} initialized with handlers: {", ".join(sorted(self.event_handlers))}')
        if self.name not in self.wildcard_handlers:  # Populate/compile wildcard patterns once per class
            self.wildcard_handlers[self.name] = wildcard_handlers = {}
            for key, handler in self.event_handlers.items():
                if isinstance(key, str) and any(c in key for c in '*?[]'):
                    wildcard_handlers[_compile_pattern(key)] = handler

    def __repr__(self):
        return f'<{self.__class__.__name__}[{self.name}][{self.primary=!r}][handlers: {len(self.event_handlers)}]>'

    def __iter__(self):
        return self

    def __next__(self) -> tuple[str, dict[str, Any]]:
        # self.log.debug(f'[View#{self._view_num}] Calling self.window.read...', extra={'color': 11})
        event, data = self.window.read()
        # self.log.debug(f'[View#{self._view_num}] Read {event=}', extra={'color': 10})
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
    def start(cls, cls_kwargs=None, init_event: tuple[Event, EventData] = None, interactive: bool = False, **kwargs):
        if cls.active_view is not None:
            raise RuntimeError(f'{cls.active_view!r} is already active - only one view may be active at a time')
        theme(cls.config['theme'])
        cls._primary_kwargs.update(kwargs)
        if size := kwargs.get('size'):
            cls._window_size = size

        obj = cls(**cls_kwargs) if cls_kwargs else cls()
        obj.render()
        if init_event:
            obj.window.write_event_value(*init_event)  # Note: data[event] => the EventData value passed here

        if not interactive:
            while True:
                try:
                    event, data = next(cls.active_view)  # noqa
                    cls.active_view.handle_event(event, data)  # noqa
                except StopIteration:
                    break

            cls.window.close()

    @classmethod
    def _handle_next(cls):
        event, data = next(cls.active_view)  # noqa
        cls.active_view.handle_event(event, data)  # noqa

    def _find_handler(self, event: Event):
        try:
            return self.event_handlers[event]
        except KeyError:
            if isinstance(event, str):
                for matches, handler in self.wildcard_handlers[self.name].items():  # noqa
                    if matches(event):
                        return handler
                if m := self._ele_event_match(event):
                    try:
                        return self._find_handler(m.group(2))
                    except NoEventHandlerRegistered:
                        pass  # Raise the exception for the full event
            elif event and isinstance(event, tuple) and isinstance(event_0 := event[0], str):
                try:
                    return self._find_handler(event_0)
                except NoEventHandlerRegistered:
                    pass  # Raise the exception for the full event

            for cls in self.__class__.mro():
                if (handler := getattr(cls, 'default_handler', None)) is not None:
                    return handler

        raise NoEventHandlerRegistered(self, event)

    def _handle_event(self, event: Event, data: EventData):
        handler = self._find_handler(event)
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

    def handle_event(self, event: Event, data: EventData):
        try:
            return self._handle_event(event, data)
        except NoEventHandlerRegistered as e:
            if not self.permissive_handler_names:
                if self.allow_no_handler:
                    self.log.warning(e, extra={'color': 'red'})
                    return
                raise
        try:
            return self._handle_event(event.lower().replace(' ', '_'), data)
        except NoEventHandlerRegistered as e:
            if self.allow_no_handler:
                self.log.warning(e, extra={'color': 'red'})
            else:
                raise

    @abstractmethod
    def get_render_args(self) -> RenderArgs:
        return NotImplemented

    def _create_window(self, layout: Layout, kwargs: Kwargs) -> Window:
        # self.log.debug(f'Create window initial {kwargs=}')
        old_window = None if (last_view := GuiView.active_view) is None else last_view.window
        popup_pos = None

        if self.primary:
            base_kwargs = deepcopy(self._primary_kwargs)
            if old_window is not None:
                base_kwargs['size'] = old_window.size
                base_kwargs['location'] = old_window.current_location()
            elif self.config['remember_pos'] and (pos := self.config.get('window_pos', type=tuple)):
                base_kwargs['location'] = pos

            # self.log.debug(f'Base kwargs={base_kwargs}')
            kwargs = base_kwargs | kwargs
        else:
            kwargs.setdefault('keep_on_top', True)
            kwargs.setdefault('modal', True)
            if old_window is not None:  # At least initially place its top-left corner on the same window; center below
                popup_pos = old_window.current_location() or self._window_pos
                kwargs.setdefault('location', popup_pos)

        kwargs.setdefault('margins', (5, 5))
        # self.log.debug(f'Initializing window with {kwargs=}')
        new_window = Window(layout=layout, finalize=True, **kwargs)
        new_window.bind('<Configure>', 'config_changed')  # Capture window size change as an event

        if self.primary:
            if old_window is not None:
                old_window.close()
                del old_window

            self.log.debug(f'Replacing GuiView.active_view={last_view.name if last_view else last_view}')
            GuiView.active_view = self
        elif popup_pos:
            new_window.move(*self._get_center(new_window.size))
            # new_pos = new_window.current_location()
            # self.log.debug(f'Popup position after moving: {new_pos=} geometry={new_window.TKroot.geometry()}')

        return new_window

    def _log_event(self, event):
        self.log.warning(f'Event: {event}.__dict__={event.__dict__}', extra={'color': 14})

    def _get_monitor(self, x: int, y: int) -> Optional[Monitor]:
        for m in self._monitors:
            if m.x <= x <= m.x + m.width and m.y <= y <= m.y + m.height:
                return m
        return None

    @property
    def monitor(self) -> Monitor:
        if monitor := self._monitor:
            return monitor
        x, y = pos = self.window.current_location()
        if monitor := self._get_monitor(x, y):
            self._monitor = monitor
            return monitor
        self.__class__._monitors = get_monitors()  # Maybe a monitor was added/removed - refresh known monitors
        if monitor := self._get_monitor(x, y):
            self._monitor = monitor
            return monitor
        raise MonitorDetectionError(f'Unable to determine monitor for window {pos=} from monitors={self._monitors}')

    def _get_center(self, size: tuple[int, int]) -> tuple[int, int]:
        own_w, own_h = size
        own_h += 30  # Title bar size on Windows 10
        if self.parent and (parent_window := self.parent.window):
            x, y = parent_window.current_location() or self._window_pos
            # self.log.debug(f'Initial pos=({x}, {y}) {size=}')
            monitor = self._get_monitor(x, y)
            par_w, par_h = parent_window.size
            x += (par_w - own_w) // 2
            y += (par_h - own_h) // 2
            # self.log.debug(f'Centered on parent pos=({x}, {y})')
        else:
            x, y = self.window.current_location() or self._window_pos
            monitor = self._get_monitor(x, y)

        if monitor:
            x_min = monitor.x
            x_max = x_min + monitor.width
            y_min = monitor.y
            y_max = y_min + monitor.height
            if x < x_min or (x + own_w) > x_max:
                x = x_min + (monitor.width - own_w) // 2
            if y < y_min or (y + own_h) > y_max:
                y = y_min + (monitor.height - own_h) // 2
            # self.log.debug(f'Centered on monitor pos=({x}, {y})')

        return 0 if x < 0 else x, 0 if y < 0 else y

    def render(self):
        render_args = self.get_render_args()
        if isinstance(render_args, tuple):
            try:
                layout, kwargs = render_args
            except ValueError:
                try:
                    layout, kwargs, ele_binds = render_args
                except ValueError:
                    raise ValueError(f'Invalid render_args returned by view={self.name!r}: {render_args}')
            else:
                ele_binds = {}
        elif isinstance(render_args, list):
            layout = render_args
            kwargs, ele_binds = {}, {}
        else:
            raise TypeError(f'Invalid render_args returned by view={self.name!r}: {render_args}')

        loc = GuiView if self.primary else self
        loc.window = self._create_window(layout, kwargs)
        loc._window_size = self.window.size
        for key, val in self.binds.items():
            self.window.bind(key, val)
        for ele_key, binds in ele_binds.items():
            ele = self.window[ele_key]
            for key, val in binds.items():
                ele.bind(key, val)

        self._log_position_and_dimensions('Rendered', False)
        self.post_render()

    def post_render(self):
        pass

    def is_maximized(self):
        return self.window.TKroot.state() == 'zoomed'

    @event_handler
    def config_changed(self, event: Event, data: EventData):
        """
        Event handler for window configuration changes.
        Known triggers: resize window, move window, window gains focus, scroll
        """
        # self.log.debug(f'Handling config_changed {event=}')
        loc = GuiView if self.primary else self
        if (new_pos := loc.window.current_location()) and new_pos != loc._window_pos:
            # self._log_position_and_dimensions('Moved', True)
            self._monitor = None
            loc._window_pos = new_pos
            if self.primary and self.config['remember_pos']:
                loc.config['window_pos'] = new_pos

        old_size = loc._window_size
        new_size = loc.window.size
        if old_size != new_size:
            loc._window_size = new_size
            # self.log.debug(f'Window size changed: {old_size} -> {new_size}')
            if handler := self.event_handlers.get('window_resized'):
                handler(self, event, {'old_size': old_size, 'new_size': new_size})  # original data is empty

    def _log_position_and_dimensions(self, prefix: str = 'Dimensions:', corners: bool = False):
        window = self.window
        win_x, win_y = win_pos = window.current_location()
        win_w, win_h = win_size = window.size
        monitor = self.monitor
        mon_x, mon_y = mon_pos = monitor.x, monitor.y
        mon_w, mon_h = mon_size = monitor.width, monitor.height
        self.log.debug(
            f'{prefix} {self} @ pos={win_pos} size={win_size} geometry={window.TKroot.geometry()}'
            f' on monitor @ pos={mon_pos} size={mon_size}'
        )
        if corners:
            win_corners = [(win_x, win_y), (win_x + win_w, win_y + win_h)]
            mon_corners = [(mon_x, mon_y), (mon_x + mon_w, mon_y + mon_h)]
            self.log.debug(f'Monitor corners={mon_corners}  Window corners={win_corners}')

    @classmethod
    def start_task(cls, func: Callable, args=(), kwargs=None, spinner_img=LoadingSpinner.blue_dots, **spin_kwargs):
        with Spinner(spinner_img, **spin_kwargs) as spinner:
            t = Thread(target=func, args=args, kwargs=kwargs)
            t.start()
            t.join(0.05)
            while t.is_alive():
                try:
                    future, func, args, kwargs = cls.pending_prompts.get(timeout=0.05)
                except Empty:
                    pass
                else:
                    if future.set_running_or_notify_cancel():
                        try:
                            result = func(*args, **kwargs)
                        except Exception as e:
                            future.set_exception(e)
                        else:
                            future.set_result(result)

                spinner.update()
