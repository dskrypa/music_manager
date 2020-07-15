
import sys
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter

from .exceptions import ArgError


class _ShellArgParser(ArgumentParser):
    """Raises an exception on errors instead of exiting"""
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('formatter_class', ArgumentDefaultsHelpFormatter)
        super().__init__(*args, **kwargs)

    def exit(self, status=0, message=None):
        raise ArgError(message)

    def error(self, message: str):
        self.print_usage(sys.stderr)
        raise ArgError(f'{self.prog}: error: {message}')
