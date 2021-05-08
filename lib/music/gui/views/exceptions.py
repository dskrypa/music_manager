class GuiError(Exception):
    """Base exception class for GUI-related errors"""


class NoEventHandlerRegistered(GuiError):
    """Exception to be raised when no event handler is registered for a given event"""
    def __init__(self, view, event):
        self.view = view
        self.event = event

    def __str__(self):
        return f'{self.view}: No handler for event={self.event!r}'


class MonitorDetectionError(GuiError):
    """Exception to be raised when unable to determine which monitor is displaying the active window"""
