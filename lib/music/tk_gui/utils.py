"""
Utils for the Tkinter GUI package.

:author: Doug Skrypa
"""

import tkinter.constants as tkc
from abc import abstractmethod
from enum import Enum
from typing import TYPE_CHECKING, Optional, Protocol, TypeVar, Type, Any, Callable, runtime_checkable

if TYPE_CHECKING:
    from tkinter import Event

__all__ = ['BindTargets', 'Anchor', 'Inheritable', 'XY', 'BindCallback', 'BindEvent', 'EventCallback']

T_co = TypeVar('T_co', covariant=True)
BindCallback = Callable[['Event'], Any]
EventCallback = Callable[['Event', ...], Any]
XY = tuple[int, int]
# fmt: off
ANCHOR_ALIASES = {
    'center': 'MID_CENTER', 'top': 'TOP_CENTER', 'bottom': 'BOTTOM_CENTER', 'left': 'MID_LEFT', 'right': 'MID_RIGHT',
    'c': 'MID_CENTER', 't': 'TOP_CENTER', 'b': 'BOTTOM_CENTER', 'l': 'MID_LEFT', 'r': 'MID_RIGHT',
}
# fmt: on


class BindEvent(Enum):
    def __new__(cls, tk_event: str):
        # Defined __new__ to avoid juggling dicts for the event names, and to avoid conflicting event names from being
        # used to initialize incorrect BindEvents
        obj = object.__new__(cls)
        obj.event = tk_event
        obj._value_ = 2 ** len(cls.__members__)
        return obj

    POSITION_CHANGED = '<Configure>'
    SIZE_CHANGED = '<Configure>'

    @classmethod
    def _missing_(cls, value: str):
        try:
            return cls[value.upper()]
        except KeyError:
            return None


class BindTargets(Enum):
    EXIT = 'exit'

    @classmethod
    def _missing_(cls, value: str):
        try:
            return cls[value.upper()]
        except KeyError:
            return None


class Anchor(Enum):
    TOP_LEFT = tkc.NW
    TOP_CENTER = tkc.N
    TOP_RIGHT = tkc.NE
    MID_LEFT = tkc.W
    MID_CENTER = tkc.CENTER
    MID_RIGHT = tkc.E
    BOTTOM_LEFT = tkc.SW
    BOTTOM_CENTER = tkc.S
    BOTTOM_RIGHT = tkc.SE

    @classmethod
    def _missing_(cls, value: str):
        aliases = ANCHOR_ALIASES
        try:
            return cls[aliases[value.lower()]]
        except KeyError:
            pass
        try:
            return cls[value.upper().replace(' ', '_')]
        except KeyError:
            return None  # This is what the default implementation does to signal an exception should be raised

    def as_justify(self):
        if self.value in (tkc.NW, tkc.W, tkc.SW):
            return tkc.LEFT
        # elif self.value in (tkc.N, tkc.CENTER, tkc.S):
        #     return tkc.CENTER
        elif self.value in (tkc.NE, tkc.E, tkc.SE):
            return tkc.RIGHT
        return tkc.CENTER


@runtime_checkable
class HasParent(Protocol[T_co]):
    __slots__ = ()

    @property
    @abstractmethod
    def parent(self) -> T_co:
        pass


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
