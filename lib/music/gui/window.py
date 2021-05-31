"""
Extended Window class from PySimpleGUI

:author: Doug Skrypa
"""

import signal
from typing import Callable
from weakref import WeakSet

from PySimpleGUI import Window as _Window

__all__ = ['Window']


class Window(_Window):
    __instances = WeakSet()

    def __init__(self, *args, finalize_callback: Callable = None, **kwargs):
        self._finalize_callback = finalize_callback
        super().__init__(*args, **kwargs)
        self.__instances.add(self)

    def _sigint_fix(self):
        """Continuously re-registers itself to be called every 250ms so that Ctrl+C is able to exit tk's mainloop"""
        self.TKroot.after(250, self._sigint_fix)

    def finalize(self):
        super().finalize()
        self.TKroot.after(250, self._sigint_fix)
        if (callback := self._finalize_callback) is not None:
            callback()
        return self

    Finalize = finalize

    @classmethod
    def unregister_sigint_handler(cls):
        signal.signal(signal.SIGINT, signal.SIG_DFL)

    @classmethod
    def _handle_sigint(cls, *args):
        """
        With just the _sigint_fix loop, the tkinter stdlib python code ignores SIGINT - this is required to actually
        handle it immediately.
        """
        for inst in cls.__instances:
            inst.write_event_value(None, None)

    def is_maximized(self) -> bool:
        return self.TKroot.state() == 'zoomed'


signal.signal(signal.SIGINT, Window._handle_sigint)
