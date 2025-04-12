"""
Utilities for formatting gui elements.

:author: Doug Skrypa
"""

from __future__ import annotations

import logging
import sys
from abc import ABC, abstractmethod
from contextlib import contextmanager
from typing import Union, Set
from weakref import WeakSet

from FreeSimpleGUI import Element, Input, Output, Multiline, Listbox, Checkbox, Text

from ds_tools.logging import DatetimeFormatter, ENTRY_FMT_DETAILED

__all__ = [
    'resize_text_column',
    'make_checkbox_grid',
    'ViewLoggerAdapter',
    'OutputHandler',
    'output_log_handler',
    'update_color',
    'padding',
    'FinishInitMixin',
]
log = logging.getLogger(__name__)


def resize_text_column(rows: list[list[Union[Text, Element]]], column: int = 0):
    if rows:
        longest = max(map(len, (row[column].DisplayText for row in rows)))
        for row in rows:
            row[column].Size = (longest, 1)

    return rows


def make_checkbox_grid(rows: list[list[Checkbox]]):
    if len(rows) > 1 and len(rows[-1]) == 1:
        last_row = rows[-1]
        rows = rows[:-1]
    else:
        last_row = None

    shortest_row = min(map(len, (row for row in rows)))
    longest_boxes = [max(map(len, (row[column].Text for row in rows))) for column in range(shortest_row)]
    for row in rows:
        for column, width in enumerate(longest_boxes):
            row[column].Size = (width, 1)

    if last_row is not None:
        rows.append(last_row)
    return rows


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


def padding(ele: Element) -> dict[str, int]:
    x, y = ele.Pad if ele.Pad is not None else ele.ParentForm.ElementPadding
    return {'padx': x, 'pady': y}


class FinishInitMixin(ABC):
    __instances: Set[FinishInitMixin] = WeakSet()

    def __init__(self):
        # log.debug(f'Registered to re-finalize: {self}')
        self.__instances.add(self)

    @abstractmethod
    def finish_init(self):
        raise NotImplementedError

    @classmethod
    def finish_init_all(cls):
        for inst in tuple(cls.__instances):
            inst.finish_init()
            cls.__instances.remove(inst)
