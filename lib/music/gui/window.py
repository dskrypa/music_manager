"""
Extended Window class from PySimpleGUI

:author: Doug Skrypa
"""

import logging
import signal
from typing import Callable
from weakref import WeakSet

from PySimpleGUI import Window as _Window

from .utils import FinishInitMixin

__all__ = ['Window']
log = logging.getLogger(__name__)


class Window(_Window):
    __registered_sigint_handler = None
    __instances = WeakSet()

    def __init__(self, *args, finalize_callback: Callable = None, **kwargs):
        if self.__registered_sigint_handler is None:
            self.register_sigint_handler()
        self._finalize_callback = finalize_callback
        super().__init__(*args, **kwargs)
        self.__instances.add(self)

    def _sigint_fix(self):
        """Continuously re-registers itself to be called every 250ms so that Ctrl+C is able to exit tk's mainloop"""
        self.TKroot.after(250, self._sigint_fix)

    def finalize(self):
        super().finalize()
        FinishInitMixin.finish_init_all()
        self.TKroot.after(250, self._sigint_fix)
        if (callback := self._finalize_callback) is not None:
            callback()
        return self

    Finalize = finalize

    @classmethod
    def unregister_sigint_handler(cls):
        if cls.__registered_sigint_handler:
            signal.signal(signal.SIGINT, signal.SIG_DFL)
        cls.__registered_sigint_handler = False

    @classmethod
    def register_sigint_handler(cls):
        log.debug('Registering Window._handle_sigint to handle SIGINT')
        signal.signal(signal.SIGINT, Window._handle_sigint)
        cls.__registered_sigint_handler = True

    @classmethod
    def _handle_sigint(cls, *args):
        """
        With just the _sigint_fix loop, the tkinter stdlib python code ignores SIGINT - this is required to actually
        handle it immediately.
        """
        for inst in cls.__instances:
            try:
                inst.write_event_value(None, None)
            except AttributeError:
                pass

    def is_maximized(self) -> bool:
        return self.TKroot.state() == 'zoomed'
