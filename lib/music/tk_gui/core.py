"""
Tkinter GUI core

:author: Doug Skrypa
"""

from __future__ import annotations

import logging
import sys
from abc import ABC, abstractmethod
from functools import partial
from inspect import stack
from os import environ
from pathlib import Path
from tkinter import Tk, Toplevel, Frame, PhotoImage, TclError, Event, CallWrapper
from typing import Optional, Union, Iterable, Type, MutableMapping
from weakref import finalize

from .assets import PYTHON_LOGO
from .positioning import positioner
from .style import Style
from .utils import BindTargets, Anchor, XY, BindCallback, BindEvent, EventCallback
from .elements.element import Element
from .pseudo_elements.row import Row

__all__ = ['RowContainer', 'Window']
log = logging.getLogger(__name__)

Bindable = Union[BindEvent, str]
BindTarget = Union[BindCallback, EventCallback, BindTargets, str, None]


class RowContainer(ABC):
    def __init__(
        self,
        layout: Iterable[Iterable[Element]] = None,
        *,
        style: Style = None,
        element_justification: Union[str, Anchor] = None,
        element_padding: XY = None,
        element_size: XY = None,
    ):
        self.style = Style.get(style)
        self.element_justification = Anchor(element_justification) if element_justification else Anchor.MID_CENTER
        self.element_padding = element_padding
        self.element_size = element_size
        self.rows = [Row(self, row) for row in layout] if layout else []

    @property
    @abstractmethod
    def tk_container(self) -> Union[Frame, Toplevel]:
        raise NotImplementedError

    @property
    @abstractmethod
    def window(self) -> Window:
        raise NotImplementedError

    def __getitem__(self, index: int) -> Row:
        return self.rows[index]


def _tk_event_handler(tk_event: str):
    return partial(_TkEventHandler, tk_event)


class _TkEventHandler:
    __slots__ = ('tk_event', 'func')

    def __init__(self, tk_event: str, func: BindCallback):
        self.tk_event = tk_event
        self.func = func

    def __set_name__(self, owner: Type[Window], name: str):
        owner._tk_event_handlers[self.tk_event] = name
        setattr(owner, name, self.func)  # replace wrapper with the original function


class Window(RowContainer):
    __hidden_root = None
    _tk_event_handlers: dict[str, str] = {}
    _finalizer: finalize
    root: Optional[Toplevel] = None

    def __init__(
        self,
        title: str = None,
        layout: Iterable[Iterable[Element]] = None,
        *,
        style: Style = None,
        size: XY = None,
        position: XY = None,
        resizable: bool = True,
        keep_on_top: bool = False,
        can_minimize: bool = True,
        transparent_color: str = None,
        alpha_channel: int = None,
        icon: bytes = None,
        modal: bool = False,
        no_title_bar: bool = False,
        margins: XY = (10, 5),  # x, y
        element_justification: Union[str, Anchor] = None,
        element_padding: XY = None,
        element_size: XY = None,
        binds: MutableMapping[str, BindTarget] = None,
    ):
        if title is None:
            try:
                # title = Path(inspect.getsourcefile(inspect.stack()[-1][0])).stem.replace('_', ' ').title()
                title = Path(stack()[-1].filename).stem.replace('_', ' ').title()
            except Exception:  # noqa
                title = ''
        self.title = title
        super().__init__(
            layout,
            style=style,
            element_justification=element_justification,
            element_padding=element_padding,
            element_size=element_size,
        )
        self._size = size
        self._position = position
        self._event_cbs: dict[BindEvent, EventCallback] = {}
        self._bound_for_events: set[str] = set()
        self._motion_end_cb_id = None
        self._last_known_pos: Optional[XY] = None
        self._last_known_size: Optional[XY] = None
        self.resizable = resizable
        self.keep_on_top = keep_on_top
        self.can_minimize = can_minimize
        self.transparent_color = transparent_color
        self.alpha_channel = alpha_channel
        self.icon = icon or PYTHON_LOGO
        self.modal = modal
        self.no_title_bar = no_title_bar
        self.margins = margins
        self.binds = binds or {}
        if self.rows:
            self.show()

    def run(self, n: int = 0):
        try:
            self.root.mainloop(n)
        except AttributeError:
            self.show()
            self.root.mainloop(n)

    @property
    def tk_container(self) -> Toplevel:
        return self.root

    @property
    def window(self) -> Window:
        return self

    def set_alpha(self, alpha: int):
        try:
            self.root.attributes('-alpha', alpha)
        except (TclError, RuntimeError):
            log.debug(f'Error setting window alpha color to {alpha!r}:', exc_info=True)

    def set_title(self, title: str):
        self.root.wm_title(title)

    # region Size & Position Methods

    @property
    def size(self) -> XY:
        root = self.root
        root.update_idletasks()
        return root.winfo_width(), root.winfo_height()

    @size.setter
    def size(self, size: XY):
        self.root.geometry('{}x{}'.format(*size))

    @property
    def true_size(self) -> XY:
        x, y = self.root.geometry().split('+', 1)[0].split('x', 1)
        return int(x), int(y)

    def set_min_size(self, width: int, height: int):
        root = self.root
        root.minsize(width, height)
        root.update_idletasks()

    @property
    def position(self) -> XY:
        root = self.root
        # root.update_idletasks()
        return root.winfo_x(), root.winfo_y()

    @position.setter
    def position(self, pos: XY):
        root = self.root
        root.geometry('+{}+{}'.format(*pos))
        # root.x root.y = pos
        root.update_idletasks()

    @property
    def true_position(self) -> XY:
        x, y = self.root.geometry().rsplit('+', 2)[1:]
        return int(x), int(y)

    @property
    def true_size_and_pos(self) -> tuple[XY, XY]:
        root = self.root
        root.update_idletasks()
        size, pos = root.geometry().split('+', 1)
        w, h = size.split('x', 1)
        x, y = pos.split('+', 1)
        return (int(w), int(h)), (int(x), int(y))

    def _outer_size(self) -> XY:
        # Outer dimensions of the window, used for calculating relative position
        width, height = self.size
        if not self.no_title_bar:
            height += 30  # Title bar size on Windows 10; more info would be needed for portability
        return width, height

    def move_to_center(self, other: Window = None):
        """
        Move this Window to the center of the monitor on which it is being displayed, or to the center of the specified
        other Window.

        :param other: A :class:`.Window`
        """
        win_w, win_h = self._outer_size()
        if other:
            x, y = other.position
            monitor = positioner.get_monitor(x, y)
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
            monitor = positioner.get_monitor(*self.position)
            x = monitor.x + (monitor.width - win_w) // 2
            y = monitor.y + (monitor.height - win_h) // 2

        self.position = x, y

    # endregion

    # region Show Window Methods

    def show(self):
        # PySimpleGUI: StartupTK
        if self.__hidden_root is None:
            self._init_hidden_root()
        if self.root is not None:
            log.warning('Attempted to show window after it was already shown', stack_info=True)
            return
        self.root = root = Toplevel()
        self._finalizer = finalize(self, self._close, root)

        self.set_alpha(0)  # Hide window while building it

        if (bg := self.style.bg.default) is not None:
            root.configure(background=bg)
        if not self.resizable:
            root.resizable(False, False)

        if not self.can_minimize:
            root.attributes('-toolwindow', 1)
        if self.keep_on_top:
            root.attributes('-topmost', 1)
        if self.transparent_color is not None:
            try:
                root.attributes('-transparentcolor', self.transparent_color)
            except (TclError, RuntimeError):
                log.error('Transparent window color not supported on this platform (Windows only)')

        # region PySimpleGUI:_convert_window_to_tk

        root.wm_title(self.title)
        # skip: PySimpleGUI:InitializeResults
        for row in self.rows:  # PySimpleGUI: PackFormIntoFrame(window, master, window)
            row.pack()
        root.configure(padx=self.margins[0], pady=self.margins[1])

        if self._size:
            self.size = self._size

        if self._position:
            self.position = self._position
        else:
            self.move_to_center()

        if self.no_title_bar:
            try:
                if sys.platform.startswith('linux'):
                    root.wm_attributes('-type', 'dock')
                else:
                    root.wm_overrideredirect(True)
            except (TclError, RuntimeError):
                log.warning('Error while disabling title bar:', exc_info=True)

        # endregion

        root.tk.call('wm', 'iconphoto', root._w, PhotoImage(data=self.icon))  # noqa

        self.set_alpha(1 if self.alpha_channel is None else self.alpha_channel)

        if self.no_title_bar:
            root.focus_force()

        root.protocol('WM_DESTROY_WINDOW', self.close)
        root.protocol('WM_DELETE_WINDOW', self.close)
        if self.modal:
            try:  # Apparently this does not work on macs...
                root.transient()
                root.grab_set()
                root.focus_force()
            except (TclError, RuntimeError):
                log.error('Error configuring window to be modal:', exc_info=True)

        self.apply_binds()
        # root.after(250, self._sigint_fix)
        root.mainloop(1)

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

    # endregion

    # region Bind Methods

    def bind(self, event_pat: Bindable, cb: BindTarget):
        if self.root:
            self._bind(event_pat, cb)
        else:
            self.binds[event_pat] = cb

    def apply_binds(self):
        for event_pat, cb in self.binds.items():
            self._bind(event_pat, cb)

    def _bind(self, event_pat: Bindable, cb: BindTarget):
        if cb is None:
            return

        bind_event = _normalize_bind_event(event_pat)
        if isinstance(bind_event, BindEvent):
            self._bind_event(bind_event, cb)
        else:
            cb = self._normalize_bind_cb(cb)
            log.debug(f'Binding event={bind_event!r} to {cb=}')
            try:
                self.root.bind(bind_event, cb)
            except (TclError, RuntimeError) as e:
                log.error(f'Unable to bind event={bind_event!r}: {e}')
                self.root.unbind_all(bind_event)

    def _normalize_bind_cb(self, cb: BindTargets) -> BindCallback:
        if isinstance(cb, str):
            cb = BindTargets(cb)
        if isinstance(cb, BindTargets):
            if cb == BindTargets.EXIT:
                cb = self.close

        return cb

    def _bind_event(self, bind_event: BindEvent, cb: EventCallback):
        self._event_cbs[bind_event] = cb
        if (tk_event := bind_event.event) not in self._bound_for_events:
            method = getattr(self, self._tk_event_handlers[tk_event])
            self.root.bind(tk_event, method)
            self._bound_for_events.add(tk_event)

    # endregion

    # region Event Handling

    @_tk_event_handler('<Configure>')
    def handle_config_changed(self, event: Event):
        root = self.root
        if self._motion_end_cb_id:
            root.after_cancel(self._motion_end_cb_id)

        self._motion_end_cb_id = root.after(100, self._handle_motion_stopped, event)

    def _handle_motion_stopped(self, event: Event):
        # log.debug(f'Motion stopped: {event=}')
        self._motion_end_cb_id = None
        new_size, new_pos = self.true_size_and_pos  # The event x/y/size are not the final pos/size
        if new_pos != self._last_known_pos:
            # log.debug(f'  Position changed: old={self._last_known_pos}, new={new_pos}')
            self._last_known_pos = new_pos
            if cb := self._event_cbs.get(BindEvent.POSITION_CHANGED):
                cb(event, new_pos)
        # else:
        #     log.debug(f'  Position did not change: old={self._last_known_pos}, new={new_pos}')

        if new_size != self._last_known_size:
            # log.debug(f'  Size changed: old={self._last_known_size}, new={new_size}')
            self._last_known_size = new_size
            if cb := self._event_cbs.get(BindEvent.SIZE_CHANGED):
                cb(event, new_size)
        # else:
        #     log.debug(f'  Size did not change: old={self._last_known_size}, new={new_size}')

    # endregion

    # region Cleanup Methods

    @classmethod
    def _close(cls, root: Toplevel):
        log.debug('  Quitting...')
        root.quit()
        log.debug('  Updating...')
        try:
            root.update()  # Needed to actually close the window on Linux if user closed with X
        except Exception:  # noqa
            pass
        log.debug('  Destroying...')
        try:
            root.destroy()
            root.update()
        except Exception:  # noqa
            pass
        log.debug('  Done')

    def close(self, event: Event = None):
        try:
            obj, close_func, args, kwargs = self._finalizer.detach()
        except (TypeError, AttributeError):
            pass
        else:
            log.debug('Closing')
            close_func(*args, **kwargs)
            self.root = None

    @classmethod
    def __close_hidden_root(cls):
        try:
            # if cls.__hidden_finalizer.detach():  # noqa
            cls.__hidden_root.destroy()
            cls.__hidden_root = None
        except AttributeError:
            pass

    # endregion

    # def _sigint_fix(self):
    #     """Continuously re-registers itself to be called every 250ms so that Ctrl+C is able to exit tk's mainloop"""
    #     self.root.after(250, self._sigint_fix)

    @property
    def is_maximized(self) -> bool:
        return self.root.state() == 'zoomed'


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
            self.widget._report_exception()

    CallWrapper.__call__ = _cw_call


if environ.get('TK_GUI_NO_CALL_WRAPPER_PATCH', '0') != '1':
    patch_call_wrapper()
