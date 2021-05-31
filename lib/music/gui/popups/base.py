"""
View: Text Popup

:author: Doug Skrypa
"""

from abc import ABCMeta
from concurrent.futures import Future
from contextlib import contextmanager
from threading import current_thread
from typing import Mapping

from PySimpleGUI import Window

from ..base_view import event_handler, GuiView, Event, EventData, Layout, RenderArgs

__all__ = ['BasePopup']


class BasePopup(GuiView, view_name='_base_popup', primary=False, metaclass=ABCMeta):
    def __init__(
        self,
        title: str = '',
        binds: Mapping[str, str] = None,
        layout: Layout = None,
        read_timeout_ms: int = None,
        **kwargs
    ):
        super().__init__(binds=binds, read_timeout_ms=read_timeout_ms)
        self.__layout = layout
        self.title = title
        self.kwargs = kwargs
        self.result = None

    @event_handler(default=True)
    def default(self, event: Event, data: EventData):
        raise StopIteration

    def get_render_args(self) -> RenderArgs:
        return self.__layout, {'title': self.title, **self.kwargs}

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

    @classmethod
    def test_popup(cls, layout: Layout, title: str = 'Test', **kwargs):
        kwargs.setdefault('binds', {'<Escape>': 'Exit'})
        popup = cls(title=title, layout=layout, **kwargs)
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
