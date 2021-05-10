"""
Utilities for formatting gui elements.

:author: Doug Skrypa
"""

import logging
import sys
from contextlib import contextmanager
from pathlib import Path
from subprocess import Popen
from typing import Union

from PySimpleGUI import Element, Input, Output, Multiline, Listbox

from ds_tools.logging import DatetimeFormatter, ENTRY_FMT_DETAILED

__all__ = ['ViewLoggerAdapter', 'OutputHandler', 'output_log_handler', 'update_color', 'open_in_file_manager']
log = logging.getLogger(__name__)


class ViewLoggerAdapter(logging.LoggerAdapter):
    _path_log_map = None

    def __init__(self, view_cls):
        super().__init__(logging.getLogger(f'{view_cls.__module__}.{view_cls.__name__}'), {'view': view_cls.name})
        self._view_name = view_cls.name
        self._real_handle = self.logger.handle
        self.logger.handle = self.handle

    def handle(self, record: logging.LogRecord):
        """
        Sets the given record's name to be the full name of the module it was logged in, as if it was logged from a
        logger initialized as ``log = logging.getLogger(__name__)``.  Since the view name is added via :meth:`.process`,
        this is necessary to keep the logs consistent with the other loggers in use here.

        The :attr:`LogRecord.module<logging.LogRecord.module>` attribute only contains the last part of the module name,
        not the fully qualified version.  Manipulating that attribute to have the desired format would have required
        manipulating all LogRecords rather than just the ones written through this adapter.
        """
        if module := self.get_module(record):
            record.name = module
        return self._real_handle(record)

    @classmethod
    def get_module(cls, record: logging.LogRecord, is_retry: bool = False):
        if is_retry or cls._path_log_map is None:
            cls._path_log_map = {mod.__file__: name for name, mod in sys.modules.items() if hasattr(mod, '__file__')}
        try:
            return cls._path_log_map[record.pathname]
        except KeyError:
            return None if is_retry else cls.get_module(record, True)

    def process(self, msg, kwargs):
        return f'[view={self._view_name}] {msg}', kwargs


class OutputHandler(logging.Handler):
    def __init__(self, element: Union[Output, Multiline], level: int = logging.NOTSET):
        super().__init__(level)
        self.element = element
        self.kwargs = {'append': True} if isinstance(element, Multiline) else {}

    def emit(self, record):
        try:
            msg = self.format(record)
            self.element.update(msg + '\n', **self.kwargs)
        except RecursionError:  # See issue 36272
            raise
        except Exception:
            self.handleError(record)


@contextmanager
def output_log_handler(
    element: Union[Output, Multiline],
    logger_name: str = None,
    level: int = logging.DEBUG,
    detail: bool = False,
    logger: logging.Logger = None,
):
    handler = OutputHandler(element, level)
    if detail:
        handler.setFormatter(DatetimeFormatter(ENTRY_FMT_DETAILED, '%Y-%m-%d %H:%M:%S %Z'))

    loggers = [logging.getLogger(logger_name), logger] if logger else [logging.getLogger(logger_name)]
    for logger in loggers:
        logger.addHandler(handler)
    try:
        yield handler
    finally:
        for logger in loggers:
            logger.removeHandler(handler)


def update_color(ele: Element, fg: str = None, bg: str = None):
    if isinstance(ele, (Input, Multiline)):
        ele.update(background_color=bg, text_color=fg)
    elif isinstance(ele, Listbox):
        ele.TKListbox.configure(bg=bg, fg=fg)


def open_in_file_manager(path: Union[Path, str]):
    path = Path(path)
    if sys.platform.startswith('linux'):
        cmd = ['xdg-open', path.as_posix()]
    elif sys.platform.startswith('win'):
        if path.is_file():
            cmd = ['explorer', '/select,', str(path)]
        else:
            cmd = ['explorer', str(path)]
    else:
        cmd = ['open', path.as_posix()]

    log.debug(f'Running: {cmd}')
    Popen(cmd)
