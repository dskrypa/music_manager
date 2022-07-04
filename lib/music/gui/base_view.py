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

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from copy import deepcopy
from fnmatch import _compile_pattern  # noqa
from functools import partial, update_wrapper, cached_property
from itertools import count
from queue import Queue, Empty
from threading import Thread
from time import monotonic
from typing import TYPE_CHECKING, Any, Optional, Callable, Type, Mapping, Collection, Union

from PySimpleGUI import WIN_CLOSED, Element, theme, theme_list

from .config import GuiConfig
from .exceptions import NoEventHandlerRegistered
from .options import GuiOptions
from .positioning import positioner
from .progress import Spinner
from .utils import ViewLoggerAdapter
from .window import Window

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ['GuiView', 'event_handler', 'Event', 'EventData', 'EleBinds', 'RenderArgs']
Layout = list[list[Element]]
Event = Union[str, tuple]
EventData = dict[Union[str, int, tuple], Any]
Kwargs = dict[str, Any]
EleBinds = dict[str, dict[str, Event]]
RenderArgs = Union[Layout, tuple[Layout, Kwargs], tuple[Layout, Kwargs, EleBinds]]

DEFAULT_SETTINGS = {'remember_pos': True, 'remember_size': False, 'theme': 'DarkGrey10'}


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

    def __set_name__(self, owner: Type[GuiView], name: str):
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
    log = logging.getLogger(__name__)
    permissive_handler_names: bool = True
    allow_no_handler: bool = True
    active_view: Optional[GuiView] = None
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
    _log_clicks: bool = False
    _motion_end_cb_id = None

    # noinspection PyMethodOverriding
    def __init_subclass__(
        cls,
        view_name: str,
        primary: bool = True,
        defaults: Mapping[str, Any] = None,
        permissive_handler_names: bool = None,
        allow_no_handler: bool = None,
        config_path: Union[str, Path] = None,
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

    def __init__(self, binds: Mapping[str, str] = None, read_timeout_ms: int = None, **kwargs):
        self._init_event = kwargs.get('init_event')
        self.parent: Optional[GuiView] = None if self.primary else GuiView.active_view
        self._monitor = None
        self._view_num = next(self._counter)
        self.binds = binds or {}
        self.read_timeout_ms = read_timeout_ms
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

    def __next__(self) -> tuple[Event, EventData]:
        # self.log.debug(f'[View#{self._view_num}] Calling self.window.read...', extra={'color': 11})
        event, data = self.window.read(self.read_timeout_ms)
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
            GuiView._window_size = size

        obj = cls(init_event=init_event, **(cls_kwargs or {}))
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
        else:
            Window.unregister_sigint_handler()

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
            else:
                if self.config['remember_pos'] and (pos := self.config.get('window_pos', type=tuple)):
                    base_kwargs['location'] = pos
                if self.config['remember_size'] and (size := self.config.get('window_size', type=tuple)):
                    base_kwargs['size'] = size

            # self.log.debug(f'Base kwargs={base_kwargs}')
            kwargs = base_kwargs | kwargs
        else:
            kwargs.setdefault('keep_on_top', True)
            kwargs.setdefault('modal', True)
            get_cfg = self.config.get
            if get_cfg(f'remember_size:{self.name}') and (size := get_cfg(f'popup_size:{self.name}', type=tuple)):
                kwargs['size'] = size
            if get_cfg(f'remember_pos:{self.name}') and (pos := get_cfg(f'popup_pos:{self.name}', type=tuple)):
                kwargs['location'] = pos
            elif old_window is not None:  # Initially place its top-left corner on the same window; center below
                popup_pos = old_window.current_location() or self._window_pos
                kwargs.setdefault('location', popup_pos)

        kwargs.setdefault('margins', (5, 5))
        self.log.debug(f'Initializing window with {kwargs=}', extra={'color': 8})
        start = monotonic()
        new_window = Window(layout=layout, finalize=True, **kwargs)
        duration = monotonic() - start
        self.log.debug(f'Window finalization finished after {duration:.6f} seconds')
        new_window.bind('<Configure>', 'config_changed')  # Capture window size change as an event

        if self.primary:
            if old_window is not None:
                old_window.close()
                del old_window

            self.log.debug(f'Replacing GuiView.active_view={last_view.name if last_view else last_view}')
            GuiView.active_view = self
        elif popup_pos:
            new_window.read(1)
            new_window.move(*positioner.get_center(new_window, getattr(self.parent, 'window', None), self._window_pos))

        return new_window

    def _log_event(self, event):
        try:
            widget = event.widget
        except AttributeError:
            element, widget, geometry, pack_info = None, None, '???', '???'
        else:
            element = next((ele for ele in self.window.key_dict.values() if ele.Widget is widget), None)
            geometry = widget.winfo_geometry()
            pack_info = widget.pack_info()

        self.log.warning(
            f'Tkinter {event=}\n'
            f'    {element=}\n'
            f'    {widget=}\n'
            f'    {geometry=}  {pack_info=}\n',
            # f'    grid_location={widget.grid_location(event.x, event.y) if widget else "???"}\n'
            # f'    event.__dict__={event.__dict__}',
            extra={'color': 14}
        )

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
        loc.window = window = self._create_window(layout, kwargs)
        loc._window_size = window.size
        for key, val in self.binds.items():
            window.bind(key, val)
        if ele_binds:
            key_ele_map = window.key_dict
            for ele_key, binds in ele_binds.items():
                ele = key_ele_map[ele_key]
                for key, val in binds.items():
                    ele.bind(key, val)

        self._log_position_and_dimensions('Rendered', False)
        self.post_render()
        if self._log_clicks:
            self.window.TKroot.bind('<Button-1>', self._log_event)

    def post_render(self):
        pass

    @event_handler
    def _window_motion_stopped(self, event: Event = None, data: EventData = None):
        # self.log.debug(f'Handling motion stopped callback for config change {event=} {self._motion_end_cb_id=}')
        self._motion_end_cb_id = None
        loc = GuiView if self.primary else self
        if (new_pos := loc.window.current_location()) and new_pos != loc._window_pos:
            # self._log_position_and_dimensions('Moved', True)
            self._monitor = None
            loc._window_pos = new_pos
            if self.primary and self.config['remember_pos']:
                loc.config['window_pos'] = new_pos
            elif self.config.get(f'remember_pos:{self.name}'):
                loc.config[f'popup_pos:{self.name}'] = new_pos

        old_size = loc._window_size
        new_size = loc.window.size
        if old_size != new_size:
            loc._window_size = new_size
            if self.primary and self.config['remember_size']:
                loc.config['window_size'] = new_size
            elif self.config.get(f'remember_size:{self.name}'):
                loc.config[f'popup_size:{self.name}'] = new_size
            # self.log.debug(f'Window for {loc=} size changed: {old_size} -> {new_size}')
            if handler := self.event_handlers.get('window_resized'):
                handler(self, event, {'old_size': old_size, 'new_size': new_size})  # original data is empty

    @event_handler
    def config_changed(self, event: Event, data: EventData):
        """
        Event handler for window configuration changes.
        Known triggers: resize window, move window, window gains focus, scroll
        """
        # self.log.debug(f'Handling config_changed {event=}')
        loc = GuiView if self.primary else self
        root = loc.window.TKroot
        if self._motion_end_cb_id is not None:
            root.after_cancel(self._motion_end_cb_id)

        self._motion_end_cb_id = root.after(100, self._window_motion_stopped)

    def _log_position_and_dimensions(self, prefix: str = 'Dimensions:', corners: bool = False):
        window = self.window
        win_x, win_y = win_pos = window.current_location()
        win_w, win_h = win_size = window.size
        monitor = positioner.get_monitor(window)
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
    def start_task(cls, func: Callable, args=(), kwargs=None, spinner_img=None, **spin_kwargs):
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

    @cached_property
    def display_name(self) -> str:
        return self.name.replace('_', ' ').title()

    @event_handler
    def about(self, event: Event, data: EventData):
        from .popups.about import AboutView

        return AboutView()

    def _settings(self) -> GuiOptions:
        options = GuiOptions(self, submit='Save', title=None)
        with options.next_row() as options:
            options.add_bool('remember_pos', 'Remember Last Window Position', self.config['remember_pos'])
            options.add_bool('remember_size', 'Remember Last Window Size', self.config['remember_size'])
        with options.next_row() as options:
            options.add_dropdown('theme', 'Theme', theme_list(), self.config['theme'])
        return options

    @event_handler
    def settings(self, event: Event, data: EventData):
        from .popups.settings import SettingsView

        return SettingsView(self._settings())
