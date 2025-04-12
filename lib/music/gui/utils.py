"""
Utilities for formatting gui elements.

:author: Doug Skrypa
"""

from __future__ import annotations

import logging
import sys
from abc import ABC, abstractmethod
from weakref import WeakSet

from FreeSimpleGUI import Element, Input, Multiline, Listbox

__all__ = ['ViewLoggerAdapter', 'update_color', 'FinishInitMixin']
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


def update_color(ele: Element, fg: str = None, bg: str = None):
    if isinstance(ele, (Input, Multiline)):
        ele.update(background_color=bg, text_color=fg)
    elif isinstance(ele, Listbox):
        ele.TKListbox.configure(bg=bg, fg=fg)


class FinishInitMixin(ABC):
    __instances: set[FinishInitMixin] = WeakSet()

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
