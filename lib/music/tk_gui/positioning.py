"""
Window positioning utilities

:author: Doug Skrypa
"""

import logging
from typing import Optional

from screeninfo import get_monitors, Monitor

__all__ = ['WindowPositioner', 'positioner']
log = logging.getLogger(__name__)


class WindowPositioner:
    def __init__(self):
        self.monitors = get_monitors()

    def get_monitor(self, x: int, y: int) -> Optional[Monitor]:
        if x is None or y is None:
            return None
        for m in self.monitors:
            if m.x <= x <= m.x + m.width and m.y <= y <= m.y + m.height:
                return m
        return None


positioner = WindowPositioner()
