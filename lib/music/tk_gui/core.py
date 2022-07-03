"""
Tkinter GUI core

:author: Doug Skrypa
"""

from __future__ import annotations

import logging
import sys
from abc import ABC, abstractmethod
from inspect import stack
from os import environ
from pathlib import Path
from tkinter import Tk, Toplevel, Frame, PhotoImage, TclError, Event, CallWrapper
from typing import Optional, Union, Iterable, MutableMapping
from weakref import finalize

from .assets import PYTHON_LOGO
from .positioning import positioner
from .style import Style
from .utils import BindTargets, Anchor, XY, BindCallback
from .elements.element import Element
from .pseudo_elements.row import Row

__all__ = ['RowContainer', 'Window']
log = logging.getLogger(__name__)

BindTarget = Union[BindCallback, BindTargets, str, None]


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


class Window(RowContainer):
    __hidden_root = None
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
    def position(self) -> XY:
        root = self.root
        return root.winfo_x(), root.winfo_y()

    @position.setter
    def position(self, pos: XY):
        root = self.root
        root.geometry('+{}+{}'.format(*pos))
        # root.x root.y = pos
        root.update_idletasks()

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

    def bind(self, event_pat: str, cb: BindTarget):
        if self.root:
            self._bind(event_pat, cb)
        else:
            self.binds[event_pat] = cb

    def apply_binds(self):
        for event_pat, cb in self.binds.items():
            self._bind(event_pat, cb)

    def _bind(self, event_pat: str, cb: BindTarget):
        if cb is None:
            return
        cb = self._normalize_bind_cb(cb)
        log.debug(f'Binding event={event_pat!r} to {cb=}')
        try:
            self.root.bind(event_pat, cb)
        except (TclError, RuntimeError) as e:
            log.error(f'Unable to bind event={event_pat!r}: {e}')
            self.root.unbind_all(event_pat)

    def _normalize_bind_cb(self, cb: BindTargets) -> BindCallback:
        if isinstance(cb, str):
            cb = BindTargets(cb)
        if isinstance(cb, BindTargets):
            if cb == BindTargets.EXIT:
                cb = self.close

        return cb

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
