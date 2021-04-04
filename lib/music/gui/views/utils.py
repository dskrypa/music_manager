"""
Utilities for formatting gui elements.

:author: Doug Skrypa
"""

import logging
import sys
from pathlib import Path
from typing import Union

from PySimpleGUI import Text, Element, Column, Input

__all__ = [
    'resize_text_column',
    'label_and_val_key',
    'label_and_diff_keys',
    'expand_columns',
    'get_a_to_b',
    'ViewLoggerAdapter',
]
log = logging.getLogger(__name__)


def resize_text_column(rows: list[list[Union[Text, Element]]], column: int = 0):
    longest = max(map(len, (row[column].DisplayText for row in rows)))
    for row in rows:
        row[column].Size = (longest, 1)

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
    src_ele = Input(src_val, disabled=True, key=f'src::{src}::{tag}', **src_kwargs)

    new_val = new_val.as_posix() if isinstance(new_val, Path) else new_val
    new_kwargs = {'size': (len(new_val), 1)} if len(new_val) > 50 else {}
    new_ele = Input(new_val, disabled=True, key=f'new::{src}::{tag}', **new_kwargs)
    return [Text(label), src_ele, Text('->'), new_ele]


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
