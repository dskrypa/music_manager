"""
Utils for the Tkinter GUI package.

:author: Doug Skrypa
"""

from __future__ import annotations

import logging
import platform
import sys
from functools import cached_property
from inspect import stack
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Type, Any, Callable, Collection

if TYPE_CHECKING:
    from .typing import HasParent

__all__ = [
    'ON_WINDOWS', 'ON_LINUX', 'ON_MAC', 'Inheritable', 'ClearableCachedPropertyMixin', 'ProgramMetadata', 'tcl_version'
]
log = logging.getLogger(__name__)

_OS = platform.system().lower()
ON_WINDOWS = _OS == 'windows'
ON_LINUX = _OS == 'linux'
ON_MAC = _OS == 'darwin'


class Inheritable:
    """An attribute whose value can be inherited from a parent"""

    __slots__ = ('parent_attr', 'default', 'type', 'name')

    def __init__(self, parent_attr: str = None, default: Any = None, type: Callable = None):  # noqa
        """
        :param parent_attr: The attribute within the parent that holds the value to inherit, if different from the
          name of this attribute.
        :param default: The default value to return when no specific value is stored in the instance, instead of
          inheriting from the parent.
        :param type: A callable used to convert new values to the expected type when this attribute is set.
        """
        self.parent_attr = parent_attr
        self.default = default
        self.type = type

    def __set_name__(self, owner: Type[HasParent], name: str):
        self.name = name

    def __get__(self, instance: Optional[HasParent], owner: Type[HasParent]):
        if instance is None:
            return self
        try:
            return instance.__dict__[self.name]
        except KeyError:
            if self.default is not None:
                return self.default
            return getattr(instance.parent, self.parent_attr or self.name)

    def __set__(self, instance: HasParent, value):
        if value is not None:
            if self.type is not None:
                value = self.type(value)
            instance.__dict__[self.name] = value


class ClearableCachedPropertyMixin:
    @classmethod
    def __cached_properties(cls) -> dict[str, cached_property]:
        cached_properties = {}
        for clz in cls.mro():
            if clz == cls:
                for k, v in cls.__dict__.items():
                    if isinstance(v, cached_property):
                        cached_properties[k] = v
            else:
                try:
                    cached_properties.update(clz.__cached_properties())  # noqa
                except AttributeError:
                    pass
        return cached_properties

    def clear_cached_properties(self, *names: str, skip: Collection[str] = None):
        if not names:
            names = self.__cached_properties()
        if skip:
            names = (name for name in names if name not in skip)
        for name in names:
            try:
                del self.__dict__[name]
            except KeyError:
                pass


class MetadataField:
    __slots__ = ('name',)

    def __set_name__(self, owner, name: str):
        self.name = name

    def __get__(self, instance, owner):
        if instance is None:
            return self
        return instance.globals.get(f'__{self.name}__', instance.default)


class ProgramMetadata:
    __slots__ = ('installed_via_setup', 'globals', 'path', 'name', 'default')

    author: str = MetadataField()
    version: str = MetadataField()
    url: str = MetadataField()
    author_email: str = MetadataField()

    def __init__(self, default: str = '[unknown]'):
        self.default = default
        self.installed_via_setup, self.globals, self.path = self._get_top_level()
        self.name = self._get_name()

    def _get_top_level(self) -> tuple[bool, dict[str, Any], Path]:
        try:
            return self._get_real_top_level()
        except Exception as e:  # noqa
            log.debug(f'Error determining top-level program info: {e}')
            try:
                path = Path(sys.argv[0])
            except IndexError:
                path = Path.cwd().joinpath('[unknown]')
            return False, {}, path

    def _get_real_top_level(self):  # noqa
        _stack = stack()
        top_level_frame_info = _stack[-1]
        path = Path(top_level_frame_info.filename)
        g = top_level_frame_info.frame.f_globals
        if (installed_via_setup := 'load_entry_point' in g and 'main' not in g) or path.stem == 'runpy':
            for level in reversed(_stack[:-1]):
                g = level.frame.f_globals
                if any(k in g for k in ('__author_email__', '__version__', '__url__')):
                    return installed_via_setup, g, Path(level.filename)

        return installed_via_setup, g, path

    def _get_name(self) -> str:
        path = self.path
        if self.installed_via_setup and path.name.endswith('-script.py'):
            try:
                return Path(sys.argv[0]).stem
            except IndexError:
                return path.stem[:-7]
        return path.stem


def tcl_version():
    try:
        return tcl_version._tcl_version
    except AttributeError:
        from tkinter import Tcl

        tcl_version._tcl_version = ver = Tcl().eval('info patchlevel')
        return ver
