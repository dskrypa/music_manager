"""
Tkinter GUI core

:author: Doug Skrypa
"""

from __future__ import annotations

import logging
import sys
import tkinter.constants as tkc
from abc import ABC, abstractmethod
from collections import defaultdict
from enum import Enum
from functools import cached_property
from inspect import stack
from itertools import count
from pathlib import Path
from tkinter import Tk, Toplevel, Frame, PhotoImage, Widget, TclError
from typing import Optional, Callable, Union, Iterable
from weakref import finalize

from .assets import PYTHON_LOGO
from .menu import ContextualMenu
from .positioning import positioner
from .style import Style, Font

__all__ = ['RowContainer', 'Window', 'Inheritable', 'Row', 'Element', 'Anchor']
log = logging.getLogger(__name__)

XY = tuple[int, int]
# fmt: off
ANCHOR_ALIASES = {
    'center': 'MID_CENTER', 'top': 'TOP_CENTER', 'bottom': 'BOTTOM_CENTER', 'left': 'MID_LEFT', 'right': 'MID_RIGHT',
    'c': 'MID_CENTER', 't': 'TOP_CENTER', 'b': 'BOTTOM_CENTER', 'l': 'MID_LEFT', 'r': 'MID_RIGHT',
}
# fmt: on


class Anchor(Enum):
    # The aliases can be specified as below after Python 3.10
    # __aliases = {
    #   'center': 'MID_CENTER', 'top': 'TOP_CENTER', 'bottom': 'BOTTOM_CENTER', 'left': 'MID_LEFT', 'right': 'MID_RIGHT'
    # }
    TOP_LEFT = tkc.NW
    TOP_CENTER = tkc.N
    TOP_RIGHT = tkc.NE
    MID_LEFT = tkc.W
    MID_CENTER = tkc.CENTER
    MID_RIGHT = tkc.E
    BOTTOM_LEFT = tkc.SW
    BOTTOM_CENTER = tkc.S
    BOTTOM_RIGHT = tkc.SE

    @classmethod
    def _missing_(cls, value: str):
        # aliases = cls.__aliases
        aliases = ANCHOR_ALIASES
        try:
            return cls[aliases[value.lower()]]
        except KeyError:
            pass
        try:
            return cls[value.upper().replace(' ', '_')]
        except KeyError:
            return None  # This is what the default implementation does to signal an exception should be raised

    def as_justify(self):
        if self.value in (tkc.NW, tkc.W, tkc.SW):
            return tkc.LEFT
        # elif self.value in (tkc.N, tkc.CENTER, tkc.S):
        #     return tkc.CENTER
        elif self.value in (tkc.NE, tkc.E, tkc.SE):
            return tkc.RIGHT
        return tkc.CENTER


class Inheritable:
    __slots__ = ('parent_attr', 'default', 'type', 'name')

    def __init__(self, parent_attr: str = None, default: Any = None, type: Callable = None):  # noqa
        self.parent_attr = parent_attr
        self.default = default
        self.type = type

    def __set_name__(self, owner, name: str):
        self.name = name

    def __get__(self, instance, owner):
        if instance is None:
            return self
        try:
            return instance.__dict__[self.name]
        except KeyError:
            if self.default is not None:
                return self.default
            return getattr(instance.parent, self.parent_attr or self.name)

    def __set__(self, instance, value):
        if value is not None:
            if self.type is not None:
                value = self.type(value)
            instance.__dict__[self.name] = value


class RowContainer(ABC):
    def __init__(
        self,
        layout: Iterable[Iterable[Element]] = None,
        *,
        style: Style = None,
        element_justification: Union[str, Anchor] = None,
        element_padding: XY = None,
        element_size: XY = None,
        font: Font = None,
        text_color: str = None,
        bg: str = None,
        ttk_theme: str = None,
        border_width: int = None,
    ):
        self.style = Style.get(style)
        if any(val is not None for val in (text_color, bg, font, ttk_theme, border_width)):
            self.style = Style(
                parent=self.style, font=font, ttk_theme=ttk_theme, text=text_color, bg=bg, border_width=border_width
            )
        self.element_justification = Anchor(element_justification) if element_justification else Anchor.MID_CENTER
        self.element_padding = element_padding
        self.element_size = element_size
        self.rows = [Row(self, row) for row in layout] if layout else []

    @property
    @abstractmethod
    def tk_container(self) -> Union[Frame, Toplevel]:
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
        font: Font = None,
        text_color: str = None,
        bg: str = None,
        transparent_color: str = None,
        alpha_channel: int = None,
        icon: bytes = None,
        modal: bool = False,
        no_title_bar: bool = False,
        margins: XY = (10, 5),  # x, y
        element_justification: Union[str, Anchor] = None,
        element_padding: XY = None,
        element_size: XY = None,
        ttk_theme: str = None,
        border_width: int = None,
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
            font=font,
            text_color=text_color,
            bg=bg,
            ttk_theme=ttk_theme,
            border_width=border_width,
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

    def set_alpha(self, alpha: int):
        try:
            self.root.attributes('-alpha', alpha)
        except (TclError, RuntimeError):
            log.debug(f'Error setting window alpha color to {alpha!r}:', exc_info=True)

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

    def move_to_center(self, other: Window = None):
        win_w, win_h = self.size
        if not self.no_title_bar:
            win_h += 30  # Title bar size on Windows 10
        if other:
            x, y = other.position
            monitor = positioner.get_monitor(x, y)
            par_w, par_h = other.size
            if not other.no_title_bar:
                par_h += 30
            x += (par_w - win_w) // 2
            y += (par_h - win_h) // 2
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

        root.title(self.title)
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

        root.after(250, self._sigint_fix)
        root.mainloop(1)

    @classmethod
    def _init_hidden_root(cls):
        Window.__hidden_root = hidden_root = Tk()
        hidden_root.attributes('-alpha', 0)  # Hide this window
        try:
            hidden_root.wm_overrideredirect(True)
        except Exception:  # noqa
            log.error('Error overriding redirect for hidden root:', exc_info=True)
        hidden_root.withdraw()
        Window.__hidden_finalizer = finalize(Window, Window.__close_hidden_root)

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

    def close(self):
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

    def _sigint_fix(self):
        """Continuously re-registers itself to be called every 250ms so that Ctrl+C is able to exit tk's mainloop"""
        self.root.after(250, self._sigint_fix)

    @property
    def is_maximized(self) -> bool:
        return self.root.state() == 'zoomed'


class Row:
    frame: Optional[Frame]
    element_justification = Inheritable(type=Anchor)    # type: Anchor
    element_padding = Inheritable()                     # type: XY
    element_size = Inheritable()                        # type: XY
    style = Inheritable()                               # type: Style
    auto_size_text = Inheritable()                      # type: bool

    def __init__(self, parent: RowContainer, elements: Iterable[Element]):
        self.frame = None
        self.parent = parent
        self.elements = list(elements)
        # for ele in self.elements:
        #     ele.parent = self
        self.expand = None  # Set to True only for Column elements
        self.fill = None    # Changes for Column, Separator, StatusBar

    def __getitem__(self, index: int):
        return self.elements[index]

    @property
    def anchor(self):
        return self.element_justification.value

    def pack(self):
        self.frame = frame = Frame(self.parent.tk_container)
        for ele in self.elements:
            ele.pack_into(self)
        anchor = self.anchor
        center = anchor == tkc.CENTER
        expand = self.expand if self.expand is not None else center
        fill = self.fill if self.fill is not None else tkc.BOTH if center else tkc.NONE
        frame.pack(side=tkc.TOP, anchor=anchor, padx=0, pady=0, expand=expand, fill=fill)
        if (bg := self.style.bg.default) is not None:
            frame.configure(background=bg)


class Element:
    _counters = defaultdict(count)
    parent: Optional[Row] = None
    widget: Optional[Widget] = None
    tooltip: Optional[str] = None
    right_click_menu: Optional[ContextualMenu] = None
    left_click_cb: Optional[Callable] = None

    pad = Inheritable('element_padding')                            # type: XY
    size = Inheritable('element_size')                              # type: XY
    auto_size_text = Inheritable()                                  # type: bool
    justify = Inheritable('element_justification', type=Anchor)     # type: Anchor
    style = Inheritable()                                           # type: Style

    def __init__(
        self,
        *,
        size: XY = None,
        pad: XY = None,
        style: Style = None,
        font: Font = None,
        auto_size_text: bool = None,
        border_width: int = None,
        justify: Union[str, Anchor] = None,
        visible: bool = True,
        tooltip: str = None,
        ttk_theme: str = None,
        bg: str = None,
        text_color: str = None,
        right_click_menu: ContextualMenu = None,
        left_click_cb: Callable = None,
    ):
        self.id = next(self._counters[self.__class__])
        self._visible = visible

        # Directly stored attrs that override class defaults
        if tooltip:
            self.tooltip = tooltip
        if right_click_menu:
            self.right_click_menu = right_click_menu
        if left_click_cb:
            self.left_click_cb = left_click_cb

        # Inheritable attrs
        self.pad = pad
        self.size = size
        self.auto_size_text = auto_size_text
        self.justify = justify
        self.style = Style.get(style)
        # if any(val is not None for val in (text_color, bg, font, ttk_theme, border_width)):
        if not (text_color is bg is font is ttk_theme is border_width is None):
            self.style = Style(
                parent=self.style, font=font, ttk_theme=ttk_theme, text=text_color, bg=bg, border_width=border_width
            )

    @cached_property
    def anchor(self):
        return self.justify.value

    @property
    def pad_kw(self) -> dict[str, int]:
        try:
            x, y = self.pad
        except TypeError:
            x, y = 5, 3
        return {'padx': x, 'pady': y}

    def pack_into(self, row: Row):
        self.parent = row
        self.apply_binds()

    def apply_binds(self):
        widget = self.widget
        widget.bind('<Button-3>', self.handle_right_click)

    def hide(self):
        self.widget.pack_forget()
        self._visible = False

    def show(self):
        self.widget.pack(**self.pad_kw)
        self._visible = True

    def toggle_visibility(self, show: bool = None):
        if show is None:
            show = not self._visible
        if show:
            self.show()
        else:
            self.hide()

    def handle_left_click(self, event):
        if (cb := self.left_click_cb) is not None:
            cb(event)  # TODO: finalize expected args to provide

    def handle_right_click(self, event):
        if (menu := self.right_click_menu) is not None:
            menu.show(event, self.widget.master)  # noqa
