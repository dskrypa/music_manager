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
from tkinter import TclError, Text, Entry, BaseWidget
from typing import TYPE_CHECKING, Optional, Union, Type, Any, Callable, Collection, Iterable, Sequence, Iterator

from .constants import STYLE_CONFIG_KEYS

if TYPE_CHECKING:
    from .typing import HasParent, XY

__all__ = [
    'ON_WINDOWS', 'ON_LINUX', 'ON_MAC',
    'Inheritable', 'ClearableCachedPropertyMixin', 'ProgramMetadata',
    'tcl_version', 'max_line_len', 'get_top_level', 'call_with_popped', 'get_selection_pos', 'find_descendants',
]
log = logging.getLogger(__name__)

_OS = platform.system().lower()
ON_WINDOWS = _OS == 'windows'
ON_LINUX = _OS == 'linux'
ON_MAC = _OS == 'darwin'


class Inheritable:
    """An attribute whose value can be inherited from a parent"""

    __slots__ = ('parent_attr', 'default', 'type', 'name', 'attr_name')

    def __init__(
        self, parent_attr: str = None, default: Any = None, type: Callable = None, attr_name: str = 'parent'  # noqa
    ):
        """
        :param parent_attr: The attribute within the parent that holds the value to inherit, if different from the
          name of this attribute.
        :param default: The default value to return when no specific value is stored in the instance, instead of
          inheriting from the parent.
        :param type: A callable used to convert new values to the expected type when this attribute is set.
        :param attr_name: The name of the ``parent`` attribute in this class
        """
        self.parent_attr = parent_attr
        self.default = default
        self.type = type
        self.attr_name = attr_name

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
            parent = getattr(instance, self.attr_name)
            return getattr(parent, self.parent_attr or self.name)

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


def max_line_len(lines: Collection[str]) -> int:
    if not lines:
        return 0
    return max(map(len, lines))


def get_top_level(widget: BaseWidget) -> BaseWidget:
    name = widget._w  # noqa
    return widget.nametowidget('.!'.join(name.split('.!')[:2]))


def call_with_popped(func: Callable, keys: Iterable[str], kwargs: dict[str, Any], args: Sequence[Any] = ()):
    kwargs = {key: val for key in keys if (val := kwargs.pop(key, None)) is not None}
    func(*args, **kwargs)


def extract_style(kwargs: dict[str, Any], keys: Collection[str] = STYLE_CONFIG_KEYS) -> dict[str, Any]:
    return {key: kwargs.pop(key) for key in tuple(kwargs) if key in keys}


def get_selection_pos(
    widget: Union[Entry, Text], raw: bool = False
) -> Union[XY, tuple[XY, XY], tuple[None, None], tuple[str, str]]:
    try:
        first, last = widget.index('sel.first'), widget.index('sel.last')
    except (AttributeError, TclError):
        return None, None
    if raw:
        return first, last
    try:
        return int(first), int(last)
    except ValueError:
        pass
    first_line, first_index = map(int, first.split('.', 1))
    last_line, last_index = map(int, last.split('.', 1))
    return (first_line, first_index), (last_line, last_index)


def find_descendants(widget: BaseWidget) -> Iterator[BaseWidget]:
    for child in widget.children.values():
        yield child
        yield from find_descendants(child)
