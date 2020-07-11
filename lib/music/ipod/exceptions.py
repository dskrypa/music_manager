
class AccessorError(Exception):
    pass


class iPodIOException(OSError):
    pass


class iPodFileClosed(iPodIOException):
    pass

