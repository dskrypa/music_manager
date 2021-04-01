class NoEventHandlerRegistered(Exception):
    """Exception to be raised when no event handler is registered for a given event"""
    def __init__(self, view, event):
        self.view = view
        self.event = event

    def __str__(self):
        return f'{self.view}: No handler for event={self.event!r}'
