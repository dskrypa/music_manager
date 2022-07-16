"""
Tkinter GUI Window

:author: Doug Skrypa
"""

from __future__ import annotations

import logging
from functools import partial, cached_property
from os import environ
from tkinter import Tk, Toplevel, PhotoImage, TclError, Event, CallWrapper, Frame, EventType
from typing import TYPE_CHECKING, Optional, Union, Type, Any, Iterable, Callable, overload
from weakref import finalize

from .assets import PYTHON_LOGO
from .enums import BindTargets, Anchor, Justify, Side, BindEvent
from .exceptions import DuplicateKeyError
from .positioning import positioner
from .pseudo_elements.row_container import RowContainer
from .pseudo_elements.scroll import ScrollableToplevel
from .style import Style
from .utils import ON_LINUX, ON_WINDOWS, ProgramMetadata

if TYPE_CHECKING:
    from .elements.element import Element
    from .typing import XY, BindCallback, EventCallback, Key, BindTarget, Bindable, BindMap, Layout, Bool

__all__ = ['Window']
log = logging.getLogger(__name__)

Top = Union[ScrollableToplevel, Toplevel]


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
    root: Union[Toplevel, Frame, None] = None
    _root: Optional[Top] = None
    element_map: dict[Key, Element]

    # region Init Overload

    @overload
    def __init__(
        self,
        layout: Layout = None,
        title: str = None,
        *,
        style: Style = None,
        grid: bool = False,
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
        handle_configure: Bool = False,
        exit_on_esc: Bool = False,
        scroll_y: Bool = False,
        scroll_x: Bool = False,
        scroll_y_div: float = 2,
        scroll_x_div: float = 1,
        close_cbs: Iterable[Callable] = None,
        # kill_others_on_close: Bool = False,
    ):
        ...

    # endregion

    def __init__(
        self,
        layout: Layout = None,
        title: str = None,
        *,
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
        binds: BindMap = None,
        handle_configure: Bool = False,
        exit_on_esc: Bool = False,
        close_cbs: Iterable[Callable] = None,
        **kwargs,
        # kill_others_on_close: Bool = False,
    ):
        self.title = title or ProgramMetadata('').name.replace('_', ' ').title()
        super().__init__(layout, **kwargs)
        self._size = size
        self._min_size = min_size
        self._position = position
        self._event_cbs: dict[BindEvent, EventCallback] = {}
        self._bound_for_events: set[str] = set()
        self._motion_end_cb_id = None
        self._last_known_pos: Optional[XY] = None
        self._last_known_size: Optional[XY] = None
        self.element_map = {}
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
        self.close_cbs = list(close_cbs) if close_cbs is not None else []
        if handle_configure:
            self.binds.setdefault(BindEvent.SIZE_CHANGED, None)
        if exit_on_esc:
            self.binds.setdefault('<Escape>', BindTargets.EXIT)
        # self.kill_others_on_close = kill_others_on_close
        if self.rows:
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

    def run(self, n: int = 0):
        try:
            self._root.mainloop(n)
        except AttributeError:
            self.show()
            self._root.mainloop(n)

    def interrupt(self, event: Event = None):
        self._root.quit()  # exit the TK main loop, but leave the window open

    # endregion

    # region Results

    def __getitem__(self, item: Union[Key, str, tuple[int, int]]) -> Element:
        try:
            return self.element_map[item]
        except KeyError:
            pass
        try:
            return super().__getitem__(item)
        except KeyError:
            pass
        raise KeyError(f'Invalid element key/ID / (row, column) index: {item!r}')

    @cached_property
    def results(self) -> dict[Key, Any]:
        return {key: ele.value for key, ele in self.element_map.items()}

    def get_result(self, key: Key) -> Any:
        return self.element_map[key].value

    def register_element(self, key: Key, element: Element):
        ele_map = self.element_map
        try:
            old = ele_map[key]
        except KeyError:
            ele_map[key] = element
        else:
            raise DuplicateKeyError(key, old, element, self)

    # endregion

    # region Size & Position Methods
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
        width, height = self.size
        if not self.no_title_bar:
            height += 30  # Title bar size on Windows 10; more info would be needed for portability
        return width, height

    def _set_init_size(self):
        if min_size := self._min_size:
            self.set_min_size(*min_size)
        if self._size:
            self.size = self._size
            return

        try:
            x, y = self._position
        except TypeError:
            x, y = self.position

        if not (monitor := positioner.get_monitor(x, y)):
            log.debug(f'Could not find monitor for pos={x, y}')
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
        root.geometry('+{}+{}'.format(*pos))
        # root.x root.y = pos
        root.update_idletasks()

    @property
    def true_position(self) -> XY:
        x, y = self._root.geometry().rsplit('+', 2)[1:]
        return int(x), int(y)

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

    # endregion
    # endregion

    # region Window State Methods

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
            if not self.keep_on_top:
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
        return self._root.focus_get() in self  # noqa

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
        try:
            if ON_LINUX:
                self._root.wm_attributes('-type', 'dock')
            else:
                self._root.wm_overrideredirect(True)
        except (TclError, RuntimeError):
            log.warning('Error while disabling title bar:', exc_info=True)

    def make_modal(self):
        root = self._root
        try:  # Apparently this does not work on macs...
            root.transient()
            root.grab_set()
            root.focus_force()
        except (TclError, RuntimeError):
            log.error('Error configuring window to be modal:', exc_info=True)

    # endregion

    # region Show Window Methods

    def _init_root_widget(self) -> Top:
        style = self.style
        kwargs = style.get_map(background='bg')
        scroll_y, scroll_x = self.scroll_y, self.scroll_x
        if not scroll_y and not scroll_x:
            self._root = self.root = root = Toplevel(**kwargs)
            return root

        kwargs['inner_kwargs'] = kwargs.copy()
        self._root = root = ScrollableToplevel(scroll_y=scroll_y, scroll_x=scroll_x, style=style, **kwargs)
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
        if self.keep_on_top:
            root.attributes('-topmost', 1)
        if self.transparent_color is not None:
            try:
                root.attributes('-transparentcolor', self.transparent_color)
            except (TclError, RuntimeError):
                log.error('Transparent window color not supported on this platform (Windows only)')
        return root

    def _init_pack_root(self) -> Top:
        outer = self._init_root()
        self.pack_rows()
        if (inner := self.root) != outer:
            self.pack_container(outer, inner, self._size)

        outer.configure(padx=self.margins[0], pady=self.margins[1])
        self._set_init_size()
        if self._position:
            self.position = self._position
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
            root.wm_title(self.title)
            root.tk.call('wm', 'iconphoto', root._w, PhotoImage(data=self.icon))  # noqa

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

    def hide(self):
        self._root.withdraw()

    def un_hide(self):
        self._root.deiconify()

    # endregion

    # region Bind Methods

    def bind(self, event_pat: Bindable, cb: BindTarget):
        if self._root:
            self._bind(event_pat, cb)
        else:
            self.binds[event_pat] = cb

    def apply_binds(self):
        for event_pat, cb in self.binds.items():
            self._bind(event_pat, cb)

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

        return cb

    def _bind_event(self, bind_event: BindEvent, cb: EventCallback):
        if cb is not None:
            self._event_cbs[bind_event] = cb
        if (tk_event := bind_event.event) not in self._bound_for_events:
            method = getattr(self, self._tk_event_handlers[tk_event])
            self._root.bind(tk_event, method)
            self._bound_for_events.add(tk_event)

    # endregion

    # region Event Handling

    @_tk_event_handler('<Configure>')
    def handle_config_changed(self, event: Event):
        # log.debug(f'{self}: Config changed: {event=}')
        root = self._root
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
        # log.debug(f'  Quitting: {root}')
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
        # if event and not self.has_focus:
        #     log.debug(f'Ignoring {event=} for window={self}')
        #     return
        # log.debug(f'Closing window={self} due to {event=}')
        try:
            obj, close_func, args, kwargs = self._finalizer.detach()
        except (TypeError, AttributeError):
            pass
        else:
            log.debug('Closing')
            close_func(*args, **kwargs)
            self._root = None
            for close_cb in self.close_cbs:
                close_cb()
            # if self.kill_others_on_close:
            #     self.close_all()

    @classmethod
    def __close_hidden_root(cls):
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
            # log.error('Error encountered during tkinter call:', exc_info=True)
            self.widget._report_exception()

    CallWrapper.__call__ = _cw_call


if environ.get('TK_GUI_NO_CALL_WRAPPER_PATCH', '0') != '1':
    patch_call_wrapper()
