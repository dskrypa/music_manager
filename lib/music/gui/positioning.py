"""
Window positioning utilities

:author: Doug Skrypa
"""

import logging
from functools import singledispatchmethod
from typing import Optional

from PySimpleGUI import Window
from screeninfo import get_monitors, Monitor

from .exceptions import MonitorDetectionError

__all__ = ['WindowPositioner', 'positioner']
log = logging.getLogger(__name__)
SizeOrPos = tuple[int, int]


class WindowPositioner:
    def __init__(self):
        self.monitors = get_monitors()

    @singledispatchmethod
    def get_monitor(self, x: int, y: int) -> Optional[Monitor]:
        if x is None or y is None:
            return None
        for m in self.monitors:
            if m.x <= x <= m.x + m.width and m.y <= y <= m.y + m.height:
                return m
        return None

    @get_monitor.register(Window)
    def get_monitor_for_window(self, window: Window) -> Optional[Monitor]:
        try:
            x, y = pos = window.current_location()
        except AttributeError:  # No parent window exists
            x, y = pos = 0, 0

        if monitor := self.get_monitor(x, y):
            return monitor
        self.monitors = get_monitors()  # Maybe a monitor was added/removed - refresh known monitors
        if monitor := self.get_monitor(x, y):
            return monitor
        raise MonitorDetectionError(f'Unable to determine monitor for window {pos=} from monitors={self.monitors}')

    def get_center(self, window: Window, parent: Window = None, last_pos: SizeOrPos = None) -> SizeOrPos:
        own_w, own_h = window.size
        own_h += 30  # Title bar size on Windows 10
        if parent:
            x, y = parent.current_location() or last_pos
            # log.debug(f'Initial pos=({x}, {y}) {size=}')
            monitor = self.get_monitor(x, y)
            par_w, par_h = parent.size
            x += (par_w - own_w) // 2
            y += (par_h - own_h) // 2
            # log.debug(f'Centered on parent pos=({x}, {y})')
        else:
            x, y = window.current_location() or last_pos
            monitor = self.get_monitor(x, y)

        if monitor:
            x_min = monitor.x
            x_max = x_min + monitor.width
            y_min = monitor.y
            y_max = y_min + monitor.height
            if x < x_min or (x + own_w) > x_max:
                x = x_min + (monitor.width - own_w) // 2
            if y < y_min or (y + own_h) > y_max:
                y = y_min + (monitor.height - own_h) // 2
            # log.debug(f'Centered on monitor pos=({x}, {y})')

        return 0 if x < 0 else x, 0 if y < 0 else y


positioner = WindowPositioner()
