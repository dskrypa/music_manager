"""
Tkinter GUI Window

:author: Doug Skrypa
"""

from __future__ import annotations

import logging
import tkinter as tk
from functools import partial
from os import environ
from time import monotonic
from tkinter import Tk, Toplevel, PhotoImage, TclError, Event, CallWrapper, Frame, BaseWidget
from tkinter.ttk import Sizegrip, Scrollbar, Treeview
from typing import TYPE_CHECKING, Optional, Union, Type, Any, Iterable, Callable, Literal, overload
from weakref import finalize

from PIL import ImageGrab

from .assets import PYTHON_LOGO
from .config import WindowConfigProperty
from .elements.menu import Menu
from .enums import BindTargets, Anchor, Justify, Side, BindEvent
from .exceptions import DuplicateKeyError
from .positioning import positioner, Monitor
from .pseudo_elements.row_container import RowContainer
from .pseudo_elements.scroll import ScrollableToplevel
from .style import Style, StyleSpec
from .utils import ON_LINUX, ON_WINDOWS, ProgramMetadata, extract_kwargs

if TYPE_CHECKING:
    from pathlib import Path
    from PIL.Image import Image as PILImage
    from .elements.element import Element, ElementBase
    from .typing import XY, BindCallback, EventCallback, Key, BindTarget, Bindable, BindMap, Layout, Bool, HasValue
    from .typing import TkContainer

__all__ = ['Window']
log = logging.getLogger(__name__)

Top = Union[ScrollableToplevel, Toplevel]
GrabAnywhere = Union[bool, Literal['control']]
_GRAB_ANYWHERE_IGNORE = (
    Sizegrip, Scrollbar, Treeview,
    tk.Scale, tk.Scrollbar, tk.Entry, tk.Text, tk.PanedWindow, tk.Listbox, tk.OptionMenu, tk.Button,
)
_INIT_OVERRIDE_KEYS = {
    'is_popup', 'resizable', 'keep_on_top', 'can_minimize', 'transparent_color', 'alpha_channel', 'no_title_bar',
    'modal', 'scaling', 'margins', 'icon',
}

# region Event Handling Helpers


def _tk_event_handler(tk_event: Union[str, BindEvent], always_bind: bool = False):
    return partial(_TkEventHandler, tk_event, always_bind)


class _TkEventHandler:
    __slots__ = ('tk_event', 'func', 'always_bind')

    def __init__(self, tk_event: Union[str, BindEvent], always_bind: bool, func: BindCallback):
        self.tk_event = tk_event
        self.always_bind = always_bind
        self.func = func

    def __set_name__(self, owner: Type[Window], name: str):
        bind_event = self.tk_event
        try:
            event = bind_event.event
        except AttributeError:
            event = bind_event
        owner._tk_event_handlers[event] = name
        if self.always_bind:
            owner._always_bind_events.add(bind_event)
        setattr(owner, name, self.func)  # replace wrapper with the original function


class Interrupt:
    __slots__ = ('time', 'event', 'element')

    def __init__(self, event: Event = None, element: Union[ElementBase, Element] = None, time: float = None):
        self.time = monotonic() if time is None else time
        self.event = event
        self.element = element

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__}@{self.time}[event={self.event!r}, element={self.element}]>'


class MotionTracker:
    __slots__ = ('start_pos', 'mouse_pos')

    def __init__(self, start_pos: XY, event: Event):
        self.start_pos = start_pos
        self.mouse_pos = self._mouse_position(event)

    @classmethod
    def _mouse_position(cls, event: Event) -> XY:
        widget: BaseWidget = event.widget
        x = event.x + widget.winfo_rootx()
        y = event.y + widget.winfo_rooty()
        return x, y

    def new_position(self, event: Event) -> XY:
        src_x, src_y = self.start_pos
        old_x, old_y = self.mouse_pos
        new_x, new_y = self._mouse_position(event)
        return src_x + (new_x - old_x), src_y + (new_y - old_y)


# endregion


class Window(RowContainer):
    # region Class Attrs
    config = WindowConfigProperty()
    __hidden_root = None
    _tk_event_handlers: dict[str, str] = {}
    _always_bind_events: set[BindEvent] = set()
    # endregion
    # region Instance Attrs (with defaults)
    __focus_widget: Optional[BaseWidget] = None
    _config: tuple[str, Union[str, Path, None], Optional[dict[str, Any]]] = None
    _keep_on_top: bool = False
    _last_interrupt: Interrupt = Interrupt(time=0)
    _last_known_pos: Optional[XY] = None
    _last_known_size: Optional[XY] = None
    _last_run: float = 0
    _motion_tracker: MotionTracker = None
    _motion_end_cb_id = None
    _root: Optional[Top] = None
    root: Optional[TkContainer] = None
    widget: Top = None
    grab_anywhere: GrabAnywhere = False                 #: Whether the window should move on mouse click + movement
    is_popup: bool = False                              #: Whether the window is a popup
    closed: bool = False
    icon: bytes = PYTHON_LOGO
    resizable: bool = True
    can_minimize: bool = True
    transparent_color: str = None
    alpha_channel: int = None
    no_title_bar: bool = False
    modal: bool = False
    scaling: float = None
    margins: XY = (10, 5)  # x, y
    # endregion
    # region Pure Instance Attrs
    _finalizer: finalize
    element_map: dict[Key, Element]
    # endregion

    # region Init Overload

    @overload
    def __init__(
        self,
        layout: Layout = None,
        title: str = None,
        *,
        style: StyleSpec = None,
        size: XY = None,
        min_size: XY = (200, 50),
        position: XY = None,
        resizable: Bool = True,
        keep_on_top: Bool = False,
        can_minimize: Bool = True,
        transparent_color: str = None,
        alpha_channel: int = None,
        icon: bytes = None,
        modal: Bool = False,
        no_title_bar: Bool = False,
        margins: XY = (10, 5),  # x, y
        anchor_elements: Union[str, Anchor] = None,
        text_justification: Union[str, Justify] = None,
        element_side: Union[str, Side] = None,
        element_padding: XY = None,
        element_size: XY = None,
        binds: BindMap = None,
        exit_on_esc: Bool = False,
        scroll_y: Bool = False,
        scroll_x: Bool = False,
        scroll_y_div: float = 2,
        scroll_x_div: float = 1,
        close_cbs: Iterable[Callable] = None,
        right_click_menu: Menu = None,
        scaling: float = None,
        grab_anywhere: GrabAnywhere = False,
        is_popup: Bool = False,
        config_name: str = None,                            #: Name used in config files (defaults to title)
        config_path: Union[str, Path] = None,
        config: dict[str, Any] = None,
        show: Bool = True,
        # kill_others_on_close: Bool = False,
    ):
        ...

    # endregion

    def __init__(
        self,
        layout: Layout = None,
        title: str = None,
        *,
        min_size: XY = (200, 50),
        binds: BindMap = None,
        exit_on_esc: Bool = False,
        close_cbs: Iterable[Callable] = None,
        right_click_menu: Menu = None,
        grab_anywhere: GrabAnywhere = False,
        config_name: str = None,
        config_path: Union[str, Path] = None,
        config: dict[str, Any] = None,
        style: StyleSpec = None,
        show: Bool = True,
        **kwargs,
        # kill_others_on_close: Bool = False,
    ):
        self.title = title or ProgramMetadata('').name.replace('_', ' ').title()
        cfg = extract_kwargs(kwargs, {'size', 'position'})
        self._config = (config_name or title, config_path, cfg if config is None else (config | cfg))
        self._min_size = min_size

        for key, val in extract_kwargs(kwargs, _INIT_OVERRIDE_KEYS).items():
            setattr(self, key, val)  # This needs to happen before touching self.config to have is_popup set

        super().__init__(layout, style=style or self.config.style, **kwargs)
        self._event_cbs: dict[BindEvent, EventCallback] = {}
        self._bound_for_events: set[str] = set()
        self.element_map = {}
        self.close_cbs = list(close_cbs) if close_cbs is not None else []
        self.binds = binds or {}
        if right_click_menu:
            self._right_click_menu = right_click_menu
            self.binds.setdefault(BindEvent.RIGHT_CLICK, None)
        if exit_on_esc:
            self.binds.setdefault('<Escape>', BindTargets.EXIT)

        if grab_anywhere is True:
            self.grab_anywhere = True
        elif grab_anywhere:
            if isinstance(grab_anywhere, str) and grab_anywhere.lower() == 'control':
                self.grab_anywhere = 'control'
            else:
                raise ValueError(f'Unexpected {grab_anywhere=} value')
        # self.kill_others_on_close = kill_others_on_close
        if show and self.rows:
            self.show()

    @property
    def tk_container(self) -> Union[Toplevel, Frame]:
        return self.root

    @property
    def window(self) -> Window:
        return self

    def __repr__(self) -> str:
        modal, title, title_bar = self.modal, self.title, not self.no_title_bar
        try:
            size, pos = self.true_size_and_pos
            has_focus = self.has_focus
        except AttributeError:  # No root
            size = pos = has_focus = None
        return (
            f'<{self.__class__.__name__}[{self._id}][{pos=}, {size=}, {has_focus=}, {modal=}, {title_bar=}, {title=}]>'
        )

    # region Run / Event Loop

    # TODO: Queue for higher level events, with an iterator method that yields them?  Different bind target to generate
    #  a high level event for window close / exit?  Subclass that uses that instead of the more direct exit, leaving
    #  this one without that or the higher level loop?

    def run(self, timeout: int = 0) -> Window:
        """
        :param timeout: Timeout in milliseconds.  If not specified or <= 0, then the mail loop will run until
          interrupted
        :return: Returns itself to allow chaining
        """
        try:
            root = self._root
        except AttributeError:
            self.show()
            root = self._root

        if not self._last_run:
            root.after(100, self._init_fix_focus)  # Nothing else seemed to work...

        if timeout > 0:
            interrupt_id = root.after(timeout, self.interrupt)
        else:
            interrupt_id = None

        self._last_run = monotonic()
        while not self.closed and self._last_interrupt.time < self._last_run:
            root.mainloop()

        if interrupt_id is not None:
            root.after_cancel(interrupt_id)

        # log.debug(f'Main loop exited for {self}')
        return self

    def interrupt(self, event: Event = None, element: ElementBase = None):
        self._last_interrupt = Interrupt(event, element)
        # log.debug(f'Interrupting {self} due to {event=}')
        # try:
        self._root.quit()  # exit the TK main loop, but leave the window open
        # except AttributeError:  # May occur when closing windows out of order
        #     pass

    def read(self, timeout: int) -> tuple[Optional[Key], dict[Key, Any], Optional[Event]]:
        self.run(timeout)
        interrupt = self._last_interrupt
        if (element := interrupt.element) is not None:
            try:
                key = element.key
            except AttributeError:
                key = element.id
        else:
            key = None
        return key, self.results, interrupt.event

    # endregion

    def __call__(self, *, take_focus: Bool = False) -> Window:
        """
        Update settings for this window.  Intended as a helper for using this Window as a context manager.

        Example of the intended use case::

            with self.window(take_focus=True) as window:
                window.run()
        """
        if self._root is None:
            self.show()
        if take_focus:
            self.take_focus()
        return self

    def __enter__(self) -> Window:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    # region Results

    def __getitem__(self, item: Union[Key, str, BaseWidget, tuple[int, int]]) -> Union[ElementBase, HasValue]:
        try:
            return self.element_map[item]
        except KeyError:
            pass
        try:
            return super().__getitem__(item)
        except KeyError:
            pass
        raise KeyError(f'Invalid element key/ID / (row, column) index: {item!r}')

    @property
    def results(self) -> dict[Key, Any]:
        return {key: ele.value for key, ele in self.element_map.items()}

    def get_result(self, key: Key) -> Any:
        return self.element_map[key].value

    def register_element(self, key: Key, element: Union[Element, HasValue]):
        ele_map = self.element_map
        try:
            old = ele_map[key]
        except KeyError:
            ele_map[key] = element
        else:
            raise DuplicateKeyError(key, old, element, self)

    # endregion

    # region Size

    @property
    def size(self) -> XY:
        root = self._root
        root.update_idletasks()
        return root.winfo_width(), root.winfo_height()

    @size.setter
    def size(self, size: XY):
        self._root.geometry('{}x{}'.format(*size))

    @property
    def true_size(self) -> XY:
        x, y = self._root.geometry().split('+', 1)[0].split('x', 1)
        return int(x), int(y)

    @property
    def title_bar_height(self) -> int:
        root = self._root
        return root.winfo_rooty() - root.winfo_y()

    def set_min_size(self, width: int, height: int):
        root = self._root
        root.minsize(width, height)
        root.update_idletasks()

    def set_max_size(self, width: int, height: int):
        root = self._root
        root.maxsize(width, height)
        root.update_idletasks()

    def _outer_size(self) -> XY:
        # Outer dimensions of the window, used for calculating relative position
        width, height = self.true_size
        # width, height = self.size
        if not self.no_title_bar:
            height += self.title_bar_height
            # height += 30  # Title bar size on Windows 10; more info would be needed for portability
        return width, height

    def _get_monitor(self, init: bool = False) -> Optional[Monitor]:
        if init:
            try:
                x, y = self.config.position
            except TypeError:
                x, y = self.position
        else:
            x, y = self.position

        if not (monitor := positioner.get_monitor(x, y)):
            log.debug(f'Could not find monitor for pos={x, y}')
        return monitor

    def _set_init_size(self):
        if min_size := self._min_size:
            self.set_min_size(*min_size)

        if size := self.config.size:
            self.size = size
            return
        elif not (monitor := self._get_monitor(True)):
            return

        root = self._root
        root.update_idletasks()
        width, height = root.winfo_reqwidth(), root.winfo_reqheight()
        max_width = monitor.width - 100
        max_height = monitor.height - 130
        if width < max_width and height < max_height:
            return

        if width > max_width:
            width = max_width
        if height > max_height:
            height = max_height
        self.size = (width, height)

    # endregion

    @property
    def true_size_and_pos(self) -> tuple[XY, XY]:
        root = self._root
        root.update_idletasks()
        size, pos = root.geometry().split('+', 1)
        w, h = size.split('x', 1)
        x, y = pos.split('+', 1)
        return (int(w), int(h)), (int(x), int(y))

    # region Position

    @property
    def position(self) -> XY:
        root = self._root
        # root.update_idletasks()
        return root.winfo_x(), root.winfo_y()

    @position.setter
    def position(self, pos: XY):
        root = self._root
        try:
            root.geometry('+{}+{}'.format(*pos))
            # root.x root.y = pos
            root.update_idletasks()
        except AttributeError:  # root has not been created yet
            self.config.position = pos

    @property
    def true_position(self) -> XY:
        x, y = self._root.geometry().rsplit('+', 2)[1:]
        return int(x), int(y)

    @property
    def monitor(self) -> Optional[Monitor]:
        return positioner.get_monitor(*self.position)

    def move_to_center(self, other: Window = None):
        """
        Move this Window to the center of the monitor on which it is being displayed, or to the center of the specified
        other Window.

        :param other: A :class:`.Window`
        """
        win_w, win_h = self._outer_size()
        try:
            x, y = other.position
        except (TypeError, AttributeError):
            x, y = self.position
        if not (monitor := positioner.get_monitor(x, y)):
            return
        elif other:
            par_w, par_h = other._outer_size()
            x += (par_w - win_w) // 2
            y += (par_h - win_h) // 2
            # If being centered on the window places it in a bad position, center on the monitor instead
            x_min, y_min = monitor.x, monitor.y
            x_max = x_min + monitor.width
            y_max = y_min + monitor.height
            if x < x_min or (x + win_w) > x_max:
                x = x_min + (monitor.width - win_w) // 2
            if y < y_min or (y + win_h) > y_max:
                y = y_min + (monitor.height - win_h) // 2
        else:
            x = monitor.x + (monitor.width - win_w) // 2
            y = monitor.y + (monitor.height - win_h) // 2

        self.position = x, y

    @property
    def mouse_position(self) -> XY:
        return self._root.winfo_pointerxy()

    # endregion

    # region Window State Methods

    def hide(self):
        self._root.withdraw()

    def un_hide(self):
        self._root.deiconify()

    def minimize(self):
        self._root.iconify()

    def maximize(self):
        self._root.state('zoomed')
        # self._root.attributes('-fullscreen', True)  # May be needed on Windows

    def normal(self):
        root = self._root
        if (state := root.state()) == 'iconic':
            root.deiconify()
        elif state == 'zoomed':
            root.state('normal')
            # root.attributes('-fullscreen', False)

    @property
    def is_maximized(self) -> bool:
        return self._root.state() == 'zoomed'

    def bring_to_front(self):
        root = self._root
        if ON_WINDOWS:
            root.wm_attributes('-topmost', 0)
            root.wm_attributes('-topmost', 1)
            if not self._keep_on_top:
                root.wm_attributes('-topmost', 0)
        else:
            root.lift()

    def send_to_back(self):
        self._root.lower()

    def disable(self):
        self._root.attributes('-disabled', 1)

    def enable(self):
        self._root.attributes('-disabled', 0)

    def take_focus(self):
        self._root.focus_force()

    @property
    def has_focus(self) -> bool:
        try:
            focus_widget = self._root.focus_get()
        except KeyError:
            focus_widget = None
        if focus_widget is None:  # focus_get may also return None
            return False
        return focus_widget.winfo_toplevel() == self._root

    # endregion

    # region Config / Update Methods

    def set_alpha(self, alpha: int):
        try:
            self._root.attributes('-alpha', alpha)
        except (TclError, RuntimeError):
            log.debug(f'Error setting window alpha color to {alpha!r}:', exc_info=True)

    def set_title(self, title: str):
        self._root.wm_title(title)

    def disable_title_bar(self):
        self.no_title_bar = True
        try:
            if ON_LINUX:
                self._root.wm_attributes('-type', 'dock')
            else:
                self._root.wm_overrideredirect(True)
        except (TclError, RuntimeError):
            log.warning('Error while disabling title bar:', exc_info=True)

    def enable_title_bar(self):
        self.no_title_bar = False
        root = self._root
        root.wm_title(self.title)
        root.tk.call('wm', 'iconphoto', root._w, PhotoImage(data=self.icon))  # noqa
        try:
            # if ON_LINUX:
            #     root.wm_attributes('-type', 'dock')
            # else:
            root.wm_overrideredirect(False)
        except (TclError, RuntimeError):
            log.warning('Error while enabling title bar:', exc_info=True)

    def toggle_title_bar(self):
        if self.no_title_bar:
            self.enable_title_bar()
        else:
            self.disable_title_bar()

    def make_modal(self):
        root = self._root
        try:  # Apparently this does not work on macs...
            root.transient()
            root.grab_set()
            root.focus_force()
        except (TclError, RuntimeError):
            log.error('Error configuring window to be modal:', exc_info=True)

    @property
    def keep_on_top(self) -> bool:
        return self._keep_on_top

    @keep_on_top.setter
    def keep_on_top(self, value: Bool):
        self._keep_on_top = bool(value)
        if (root := self._root) is not None:
            if value and not ON_WINDOWS:
                root.lift()  # Bring the window to the front first
            # if value:  # Bring the window to the front first
            #     if ON_WINDOWS:
            #         root.wm_attributes('-topmost', 0)
            #     else:
            #         root.lift()
            root.wm_attributes('-topmost', 1 if value else 0)

    def update_style(self, style: StyleSpec):
        self.style = Style.get_style(style)
        for element in self.all_elements:
            element.update_style()

    # endregion

    # region Show Window Methods

    def _init_root_widget(self) -> Top:
        style = self.style
        kwargs = style.get_map(background='bg')
        scroll_y, scroll_x = self.scroll_y, self.scroll_x
        if not scroll_y and not scroll_x:
            self.widget = self._root = self.root = root = Toplevel(**kwargs)
            return root

        kwargs['inner_kwargs'] = kwargs.copy()  # noqa
        self.widget = self._root = root = ScrollableToplevel(
            scroll_y=scroll_y, scroll_x=scroll_x, style=style, pad=self.margins, **kwargs
        )
        self.root = root.inner_widget
        return root

    def _init_root(self) -> Top:
        root = self._init_root_widget()
        self._finalizer = finalize(self, self._close, root)
        self.set_alpha(0)  # Hide window while building it
        if not self.resizable:
            root.resizable(False, False)
        if not self.can_minimize:
            root.attributes('-toolwindow', 1)
        if self._keep_on_top:
            root.attributes('-topmost', 1)
        if self.transparent_color is not None:
            try:
                root.attributes('-transparentcolor', self.transparent_color)
            except (TclError, RuntimeError):
                log.error('Transparent window color not supported on this platform (Windows only)')
        if (scaling := self.scaling) is not None:
            root.tk.call('tk', 'scaling', scaling)
        return root

    def _get_init_inner_size(self, inner: TkContainer) -> Optional[XY]:
        if size := self.config.size:
            return size
        x_div, y_div = self._scroll_divisors()
        if y_div <= 1 or not (monitor := self._get_monitor(True)):
            return None

        inner.update()
        width: int = inner.winfo_reqwidth() // x_div  # noqa
        height = inner.winfo_reqheight()
        max_outer_height = monitor.height - 130
        max_inner_height = max_outer_height - 50
        if height > max_outer_height / 3:
            height = min(max_inner_height, height // y_div)  # noqa

        return width, height

    def _init_pack_root(self) -> Top:
        outer = self._init_root()
        self.pack_rows()
        if (inner := self.root) != outer:  # outer is scrollable
            self.pack_container(outer, inner, self._get_init_inner_size(inner))
        else:
            outer.configure(padx=self.margins[0], pady=self.margins[1])

        self._set_init_size()
        if pos := self.config.position:
            self.position = pos
        else:
            self.move_to_center()
        return outer

    def show(self):
        if self.__hidden_root is None:
            self._init_hidden_root()
        if self._root is not None:
            log.warning('Attempted to show window after it was already shown', stack_info=True)
            return

        root = self._init_pack_root()
        if self.no_title_bar:
            self.disable_title_bar()
        else:
            self.enable_title_bar()

        self.set_alpha(1 if self.alpha_channel is None else self.alpha_channel)
        if self.no_title_bar:
            root.focus_force()
        if self.modal:
            self.make_modal()

        root.protocol('WM_DESTROY_WINDOW', self.close)
        root.protocol('WM_DELETE_WINDOW', self.close)
        self.apply_binds()
        # root.after(250, self._sigint_fix)
        root.update_idletasks()

    @classmethod
    def _init_hidden_root(cls):
        Window.__hidden_root = hidden_root = Tk()
        hidden_root.attributes('-alpha', 0)  # Hide this window
        try:
            hidden_root.wm_overrideredirect(True)
        except (TclError, RuntimeError):
            log.error('Error overriding redirect for hidden root:', exc_info=True)
        hidden_root.withdraw()
        Window.__hidden_finalizer = finalize(Window, Window.__close_hidden_root)

    def _init_fix_focus(self):
        if (widget := self.__focus_widget) is None:
            return
        if self._root.focus_get() != widget:
            log.debug(f'Setting focus on {widget}')
            widget.focus_set()

    def maybe_set_focus(self, element: Element, widget: BaseWidget = None) -> bool:
        if self.__focus_widget is not None:
            return False
        if widget is None:
            widget = element.widget
        widget.focus_set()
        self.__focus_widget = widget
        return True

    # endregion

    # region Grab Anywhere

    def _init_grab_anywhere(self):
        prefix = 'Control-' if self.grab_anywhere == 'control' else ''
        root = self._root
        root.bind(f'<{prefix}Button-1>', self._begin_grab_anywhere)
        root.bind(f'<{prefix}B1-Motion>', self._handle_grab_anywhere_motion)
        root.bind(f'<{prefix}ButtonRelease-1>', self._end_grab_anywhere)

    def _begin_grab_anywhere(self, event: Event):
        widget: BaseWidget = event.widget
        if isinstance(widget, _GRAB_ANYWHERE_IGNORE):
            return
        elif (element := self.widget_element_map.get(widget)) and element.ignore_grab:
            return
        self._motion_tracker = MotionTracker(self.true_size_and_pos[1], event)

    def _handle_grab_anywhere_motion(self, event: Event):
        try:
            self.position = self._motion_tracker.new_position(event)
        except AttributeError:  # grab anywhere already ended and _motion_tracker is None again
            pass

    def _end_grab_anywhere(self, event: Event):
        try:
            del self._motion_tracker
        except AttributeError:
            pass

    # endregion

    # region Bind Methods

    def bind(self, event_pat: Bindable, cb: BindTarget):
        """
        Register a bind callback.  If :meth:`.show` was already called, it is applied immediately, otherwise it is
        registered to be applied later.
        """
        if self._root:
            self._bind(event_pat, cb)
        else:
            self.binds[event_pat] = cb

    def apply_binds(self):
        """Called by :meth:`.show` to apply all registered callback bindings"""
        for event_pat, cb in self.binds.items():
            self._bind(event_pat, cb)

        for bind_event in self._always_bind_events:
            self._bind_event(bind_event, None)

        if self.grab_anywhere:
            self._init_grab_anywhere()

    def _bind(self, event_pat: Bindable, cb: BindTarget):
        bind_event = _normalize_bind_event(event_pat)
        if isinstance(bind_event, BindEvent):
            self._bind_event(bind_event, cb)
        elif cb is None:
            return
        else:
            cb = self._normalize_bind_cb(cb)
            log.debug(f'Binding event={bind_event!r} to {cb=}')
            try:
                self._root.bind(bind_event, cb)
            except (TclError, RuntimeError) as e:
                log.error(f'Unable to bind event={bind_event!r}: {e}')
                # self._root.unbind_all(bind_event)

    def _normalize_bind_cb(self, cb: BindTargets) -> BindCallback:
        if isinstance(cb, str):
            cb = BindTargets(cb)
        if isinstance(cb, BindTargets):
            if cb == BindTargets.EXIT:
                cb = self.close
            elif cb == BindTargets.INTERRUPT:
                cb = self.interrupt
            else:
                raise ValueError(f'Invalid {cb=} for {self}')

        return cb

    def _bind_event(self, bind_event: BindEvent, cb: Optional[EventCallback]):
        if cb is not None:
            self._event_cbs[bind_event] = cb
        if (tk_event := getattr(bind_event, 'event', bind_event)) not in self._bound_for_events:
            method = getattr(self, self._tk_event_handlers[tk_event])
            log.debug(f'Binding event={tk_event!r} to {method=}')
            self._root.bind(tk_event, method)
            self._bound_for_events.add(tk_event)

    # endregion

    # region Event Handling

    @_tk_event_handler('<Configure>', True)
    def handle_config_changed(self, event: Event):
        # log.debug(f'{self}: Config changed: {event=}')
        root = self._root
        if self._motion_end_cb_id:
            root.after_cancel(self._motion_end_cb_id)

        self._motion_end_cb_id = root.after(100, self._handle_motion_stopped, event)

    def _handle_motion_stopped(self, event: Event):
        # log.debug(f'Motion stopped: {event=}')
        self._motion_end_cb_id = None
        with self.config as config:
            new_size, new_pos = self.true_size_and_pos  # The event x/y/size are not the final pos/size
            if new_pos != self._last_known_pos:
                # log.debug(f'  Position changed: old={self._last_known_pos}, new={new_pos}')
                self._last_known_pos = new_pos
                if cb := self._event_cbs.get(BindEvent.POSITION_CHANGED):
                    cb(event, new_pos)
                # if not self.is_popup and config.remember_position:
                if config.remember_position:
                    config.position = new_pos
            # else:
            #     log.debug(f'  Position did not change: old={self._last_known_pos}, new={new_pos}')

            if new_size != self._last_known_size:
                # log.debug(f'  Size changed: old={self._last_known_size}, new={new_size}')
                self._last_known_size = new_size
                if cb := self._event_cbs.get(BindEvent.SIZE_CHANGED):
                    cb(event, new_size)
                # if not self.is_popup and config.remember_size:
                if config.remember_size:
                    config.size = new_size
            # else:
            #     log.debug(f'  Size did not change: old={self._last_known_size}, new={new_size}')

    @_tk_event_handler(BindEvent.RIGHT_CLICK)
    def handle_right_click(self, event: Event):
        if menu := self._right_click_menu:
            menu.parent = self  # Needed for style inheritance
            menu.show(event, self.root)

    @_tk_event_handler(BindEvent.MENU_RESULT, True)
    def _handle_menu_callback(self, event: Event):
        result = Menu.results.pop(event.state, None)
        log.debug(f'Menu {result=}')
        if cb := self._event_cbs.get(BindEvent.MENU_RESULT):
            cb(event, result)

    # endregion

    # region Cleanup Methods

    @classmethod
    def _close(cls, root: Toplevel):
        # TODO: If closed out of order, make sure to exit
        log.debug(f'Closing: {root}')
        # log.debug('  Quitting...')
        # log.debug(f'  Quitting: {root}')
        root.quit()
        # log.debug('  Updating...')
        try:
            root.update()  # Needed to actually close the window on Linux if user closed with X
        except Exception:  # noqa
            pass
        # log.debug('  Destroying...')
        try:
            root.destroy()
            root.update()
        except Exception:  # noqa
            pass
        # log.debug('  Done')

    def close(self, event: Event = None):
        self.closed = True
        # self.interrupt(event)  # Prevent `run` from waiting for an interrupt that will not come if closed out of order
        # if event and not self.has_focus:
        #     log.debug(f'Ignoring {event=} for window={self}')
        #     return
        # log.debug(f'Closing window={self} due to {event=}')
        try:
            obj, close_func, args, kwargs = self._finalizer.detach()
        except (TypeError, AttributeError):
            pass
        else:
            # log.debug('Closing')
            close_func(*args, **kwargs)
            self._root = None
            for close_cb in self.close_cbs:
                # log.debug(f'Calling {close_cb=}')
                close_cb()
            # if self.kill_others_on_close:
            #     self.close_all()

    @classmethod
    def __close_hidden_root(cls):
        # log.debug('Closing hidden Tk root')
        try:
            # if cls.__hidden_finalizer.detach():  # noqa
            cls.__hidden_root.destroy()
            cls.__hidden_root = None
        except AttributeError:
            pass

    # @classmethod
    # def close_all(cls):
    #     instances = tuple(cls.__instances)
    #     for window in instances:
    #         window.kill_others_on_close = False  # prevent recursive calls of this method
    #         window.close()
    #     # while cls.__instances:
    #     #     log.debug(f'Windows to close: {len(cls.__instances)}')
    #     #     try:
    #     #         window = cls.__instances.pop()
    #     #     except KeyError:
    #     #         pass
    #     #     else:
    #     #         window.kill_others_on_close = False  # prevent recursive calls of this method
    #     #         window.close()

    # endregion

    # def _sigint_fix(self):
    #     """Continuously re-registers itself to be called every 250ms so that Ctrl+C is able to exit tk's mainloop"""
    #     self._root.after(250, self._sigint_fix)

    def get_screenshot(self) -> PILImage:
        (width, height), (x, y) = self.true_size_and_pos
        if not self.no_title_bar:
            height += self.title_bar_height

        return ImageGrab.grab((x, y, x + width, y + height))


def _normalize_bind_event(event_pat: Bindable) -> Bindable:
    try:
        return BindEvent(event_pat)
    except ValueError:
        return event_pat


def patch_call_wrapper():
    """Patch CallWrapper.__call__ to prevent it from suppressing KeyboardInterrupt"""

    def _cw_call(self, *args):
        try:
            if self.subst:
                args = self.subst(*args)
            return self.func(*args)
        except Exception:  # noqa
            # The original implementation re-raises SystemExit, but uses a bare `except:` here
            # log.error('Error encountered during tkinter call:', exc_info=True)
            self.widget._report_exception()

    CallWrapper.__call__ = _cw_call


if environ.get('TK_GUI_NO_CALL_WRAPPER_PATCH', '0') != '1':
    patch_call_wrapper()
