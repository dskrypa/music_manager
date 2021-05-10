"""
View: Text Popup

:author: Doug Skrypa
"""

from concurrent.futures import Future
from contextlib import contextmanager
from threading import current_thread

from PySimpleGUI import Window

from ...base_view import event_handler, GuiView, Event, EventData

__all__ = ['BasePopup']


class BasePopup(GuiView, view_name='_base_popup', primary=False):
    def __init__(self, title: str = '', **kwargs):
        super().__init__(**kwargs)
        self.title = title
        self.result = None

    @event_handler(default=True)
    def default(self, event: Event, data: EventData):
        raise StopIteration

    def _get_result(self):
        self.render()
        self.run()
        return self.result

    def get_result(self):
        if current_thread().name == 'MainThread':
            with mainloop_fixer():
                return self._get_result()

        future = Future()
        self.pending_prompts.put((future, self._get_result, (), {}))
        return future.result()

    @classmethod
    def start_popup(cls, *args, **kwargs):
        popup = cls(*args, **kwargs)
        return popup.get_result()


@contextmanager
def mainloop_fixer():
    """
    Restores the expected mainloop in case a TK callback opened a Window (most likely as a popup) while a call to
    Window.read was still pending
    """
    original = Window._window_running_mainloop
    try:
        yield
    finally:
        if original:
            Window._window_running_mainloop = original
            Window._root_running_mainloop = original.TKroot
