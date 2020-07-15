"""
A basic shell implementation to facilitate browsing files on an iPod.

:author: Doug Skrypa
"""

import sys
from itertools import count
from typing import Optional

from prompt_toolkit import PromptSession, ANSI

from ds_tools.output import colored, Terminal
from pymobiledevice.afc.exceptions import iOSError
from tz_aware_dt import now

from ..ipod import iPod, iPath
from .completion import FileCompleter
from .exceptions import ExitLoop

__all__ = ['iPodShell']


class iPodShell:
    def __init__(self, ipod: Optional[iPod] = None):
        self.ipod = ipod or iPod.find()
        self._num = count()
        self._ps1 = '{} iPod[{}]: {} {}{} '.format(
            colored('{}', 11), colored(self.ipod.name, 14), colored('{}', 11), colored('{}', 10), colored('$', 11)
        )
        self.cwd = self.ipod.get_path('/')  # type: iPath
        self.completer = FileCompleter()
        self._term = Terminal()
        print(colored('=' * (self._term.width - 1), 6))
        self.prompt_session = PromptSession()

    def cmdloop(self, intro: Optional[str] = None):
        print(intro or f'Interactive iPod Session - Connected to: {self.ipod}')
        while True:
            try:
                self._handle_input()
            except (KeyboardInterrupt, ExitLoop):
                break

    def _handle_input(self):
        prompt = self._ps1.format(now('[%H:%M:%S]'), self.cwd, next(self._num))
        # noinspection PyTypeChecker
        if input_line := self.prompt_session.prompt(ANSI(prompt), completer=self.completer(self.cwd)).strip():
            if input_line in ('exit', 'quit'):
                raise ExitLoop
            else:
                try:
                    cmd, arg_str = input_line.split(maxsplit=1)
                except ValueError:
                    cmd = input_line
                    arg_str = ''

                try:
                    getattr(self, f'do_{cmd}')(arg_str)
                except AttributeError:
                    _stderr(f'Unknown command: {cmd}')
                except iOSError as e:
                    _stderr(f'{cmd}: error: {e}')


def _stderr(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)
