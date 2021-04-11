"""
View: Text Popup

:author: Doug Skrypa
"""

from typing import Any

from ..base import event_handler, GuiView

__all__ = ['BasePopup']


class BasePopup(GuiView, view_name='_base_popup', primary=False):
    def __init__(self, title: str = '', **kwargs):
        super().__init__(**kwargs)
        self.title = title
        self.result = None

    @event_handler(default=True)
    def default(self, event: str, data: dict[str, Any]):
        raise StopIteration

    def get_result(self):
        self.render()
        self.run()
        return self.result
