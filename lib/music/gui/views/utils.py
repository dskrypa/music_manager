"""
Utilities for formatting gui elements.

:author: Doug Skrypa
"""

import logging
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Union, Optional

from PySimpleGUI import Text, Element, Column, Input, Checkbox, Output, Multiline, theme

from ds_tools.logging import DatetimeFormatter, ENTRY_FMT_DETAILED

__all__ = [
    'resize_text_column',
    'label_and_val_key',
    'label_and_diff_keys',
    'expand_columns',
    'get_a_to_b',
    'ViewLoggerAdapter',
    'make_checkbox_grid',
    'output_log_handler',
    'OutputHandler',
    'split_key',
    'DarkInput',
]
log = logging.getLogger(__name__)


def resize_text_column(rows: list[list[Union[Text, Element]]], column: int = 0):
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


def label_and_val_key(src: str, tag: str, title: bool = True) -> tuple[Text, str]:
    label = Text(tag.replace('_', ' ').title() if title else tag, key=f'tag::{src}::{tag}')
    return label, f'val::{src}::{tag}'


def label_and_diff_keys(src: str, tag: str) -> tuple[Text, Text, Text, str, str]:
    label = Text(tag.replace('_', ' ').title(), key=f'tag::{src}::{tag}')
    sep_1 = Text('from', key=f'from::{src}::{tag}')
    sep_2 = Text('to', key=f'to::{src}::{tag}')
    return label, sep_1, sep_2, f'src::{src}::{tag}', f'new::{src}::{tag}'


def get_a_to_b(label: str, src_val: Union[str, Path], new_val: Union[str, Path], src: str, tag: str) -> list[Element]:
    src_val = src_val.as_posix() if isinstance(src_val, Path) else src_val
    src_kwargs = {'size': (len(src_val), 1)} if len(src_val) > 50 else {}
    src_ele = DarkInput(src_val, disabled=True, key=f'src::{src}::{tag}', **src_kwargs)

    new_val = new_val.as_posix() if isinstance(new_val, Path) else new_val
    new_kwargs = {'size': (len(new_val), 1)} if len(new_val) > 50 else {}
    new_ele = DarkInput(new_val, disabled=True, key=f'new::{src}::{tag}', **new_kwargs)
    return [Text(label), src_ele, Text('\u2794', font=('Helvetica', 15)), new_ele]


def expand_columns(rows: list[list[Element]]):
    for row in rows:
        for ele in row:
            if isinstance(ele, Column):
                ele.expand(True, True)
            try:
                ele_rows = ele.Rows
            except AttributeError:
                pass
            else:
                log.debug(f'Expanding columns on {ele}')
                expand_columns(ele_rows)


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
    def __init__(self, element: Union[Output, Multiline], level = logging.NOTSET):
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


def split_key(key: str) -> Optional[tuple[str, str, str]]:
    try:
        key_type, obj_key = key.split('::', 1)
        obj, item = obj_key.rsplit('::', 1)
    except Exception:
        return None
    else:
        return key_type, obj, item


class DarkInput(Input):
    def __init__(self, *args, **kwargs):
        if 'dark' in theme().lower():
            kwargs.setdefault('disabled_readonly_background_color', '#a2a2a2')
            kwargs.setdefault('disabled_readonly_text_color', '#000000')
        super().__init__(*args, **kwargs)

    def update(self, *args, disabled=None, **kwargs):
        was_enabled = self.TKEntry['state'] == 'normal'
        super().update(*args, disabled=disabled, **kwargs)
        if 'dark' in theme().lower() and not was_enabled:
            if disabled is False:
                # self.TKEntry.configure(background=self.BackgroundColor, fg=self.TextColor)
                self.TKEntry.configure(readonlybackground=self.BackgroundColor, disabledforeground=self.TextColor)
            else:
                if background_color := kwargs.get('background_color'):
                    # log.info(f'Setting {background_color=!r} for {self!r}')
                    self.TKEntry.configure(readonlybackground=background_color)
                if text_color := kwargs.get('text_color'):
                    # log.info(f'Setting {text_color=!r} for {self!r}')
                    self.TKEntry.configure(fg=text_color)
