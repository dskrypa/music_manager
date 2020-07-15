
import sys
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
from typing import Sequence, Dict, Any

from .exceptions import ArgError


class ShellArgParser(ArgumentParser):
    """Raises an exception on errors instead of exiting"""
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('formatter_class', ArgumentDefaultsHelpFormatter)
        super().__init__(*args, **kwargs)

    def exit(self, status=0, message=None):
        raise ArgError(message)

    def error(self, message: str):
        self.print_usage(sys.stderr)
        raise ArgError(f'{self.prog}: error: {message}')

    def parse_kwargs(self, args: Sequence[str]) -> Dict[str, Any]:
        args = self.parse_args(args)
        return args.__dict__
