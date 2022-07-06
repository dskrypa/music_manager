"""
Utils for the Tkinter GUI package.

:author: Doug Skrypa
"""

from __future__ import annotations

import tkinter.constants as tkc
from enum import Enum
from typing import TYPE_CHECKING, Optional, Type, Any, Callable

if TYPE_CHECKING:
    from .typing import HasParent

__all__ = ['BindTargets', 'Anchor', 'Inheritable', 'BindEvent', 'Justify', 'Side']

# fmt: off
ANCHOR_ALIASES = {
    'center': 'MID_CENTER', 'top': 'TOP_CENTER', 'bottom': 'BOTTOM_CENTER', 'left': 'MID_LEFT', 'right': 'MID_RIGHT',
    'c': 'MID_CENTER', 't': 'TOP_CENTER', 'b': 'BOTTOM_CENTER', 'l': 'MID_LEFT', 'r': 'MID_RIGHT',
}
# fmt: on


class MissingMixin:
    __aliases = None

    def __init_subclass__(cls, aliases: dict[str, str] = None):
        cls.__aliases = aliases

    @classmethod
    def _missing_(cls: Type[Enum], value: str):
        if aliases := cls.__aliases:  # noqa
            try:
                return cls[aliases[value.lower()]]
            except KeyError:
                pass
        try:
            return cls[value.upper().replace(' ', '_')]
        except KeyError:
            return None  # This is what the default implementation does to signal an exception should be raised


class BindEvent(MissingMixin, Enum):
    def __new__(cls, tk_event: str):
        # Defined __new__ to avoid juggling dicts for the event names, and to avoid conflicting event names from being
        # used to initialize incorrect BindEvents
        obj = object.__new__(cls)
        obj.event = tk_event
        obj._value_ = 2 ** len(cls.__members__)
        return obj

    POSITION_CHANGED = '<Configure>'
    SIZE_CHANGED = '<Configure>'


class BindTargets(MissingMixin, Enum):
    EXIT = 'exit'
    INTERRUPT = 'interrupt'


class Side(MissingMixin, Enum, aliases={'l': 'LEFT', 'r': 'RIGHT', 't': 'TOP', 'b': 'BOTTOM'}):
    NONE = None
    LEFT = tkc.LEFT
    RIGHT = tkc.RIGHT
    TOP = tkc.TOP
    BOTTOM = tkc.BOTTOM


class Justify(MissingMixin, Enum, aliases={'c': 'CENTER', 'l': 'LEFT', 'r': 'RIGHT'}):
    NONE = None
    LEFT = tkc.LEFT
    CENTER = tkc.CENTER
    RIGHT = tkc.RIGHT


class Anchor(MissingMixin, Enum, aliases=ANCHOR_ALIASES):
    NONE = None
    TOP_LEFT = tkc.NW
    TOP_CENTER = tkc.N
    TOP_RIGHT = tkc.NE
    MID_LEFT = tkc.W
    MID_CENTER = tkc.CENTER
    MID_RIGHT = tkc.E
    BOTTOM_LEFT = tkc.SW
    BOTTOM_CENTER = tkc.S
    BOTTOM_RIGHT = tkc.SE

    def as_justify(self):
        if self.value is None:
            return None
        elif self.value in (tkc.NW, tkc.W, tkc.SW):
            return tkc.LEFT
        # elif self.value in (tkc.N, tkc.CENTER, tkc.S):
        #     return tkc.CENTER
        elif self.value in (tkc.NE, tkc.E, tkc.SE):
            return tkc.RIGHT
        return tkc.CENTER

    def as_side(self):
        if self.value == tkc.N:
            return tkc.TOP
        elif self.value == tkc.S:
            return tkc.BOTTOM
        elif self.value in (tkc.NW, tkc.W, tkc.SW):
            return tkc.LEFT
        elif self.value in (tkc.NE, tkc.E, tkc.SE):
            return tkc.RIGHT
        return None  # None or CENTER


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
