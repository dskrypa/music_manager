"""
Enums for the Tkinter GUI package.

:author: Doug Skrypa
"""

from __future__ import annotations

import tkinter.constants as tkc
from enum import Enum, IntEnum
from typing import Type

from .utils import ON_MAC

__all__ = ['BindTargets', 'Anchor', 'BindEvent', 'Justify', 'Side', 'StyleState', 'ListBoxSelectMode']

# fmt: off
ANCHOR_ALIASES = {
    'center': 'MID_CENTER', 'top': 'TOP_CENTER', 'bottom': 'BOTTOM_CENTER', 'left': 'MID_LEFT', 'right': 'MID_RIGHT',
    'c': 'MID_CENTER', 't': 'TOP_CENTER', 'b': 'BOTTOM_CENTER', 'l': 'MID_LEFT', 'r': 'MID_RIGHT',
}
SIDE_STICKY_MAP = {tkc.LEFT: tkc.W, tkc.RIGHT: tkc.E, tkc.TOP: tkc.N, tkc.BOTTOM: tkc.S}
JUSTIFY_TO_ANCHOR = {tkc.LEFT: tkc.W, tkc.CENTER: tkc.CENTER, tkc.RIGHT: tkc.E}
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

    def __bool__(self) -> bool:
        return self._value_ is not None  # noqa


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
    RIGHT_CLICK = '<ButtonRelease-2>' if ON_MAC else '<ButtonRelease-3>'
    MENU_RESULT = '<<Custom:MenuCallback>>'


class BindTargets(MissingMixin, Enum):
    EXIT = 'exit'
    INTERRUPT = 'interrupt'


class Side(MissingMixin, Enum, aliases={'l': 'LEFT', 'r': 'RIGHT', 't': 'TOP', 'b': 'BOTTOM'}):
    NONE = None
    LEFT = tkc.LEFT
    RIGHT = tkc.RIGHT
    TOP = tkc.TOP
    BOTTOM = tkc.BOTTOM

    def as_sticky(self):
        return SIDE_STICKY_MAP.get(self.value)


class Justify(MissingMixin, Enum, aliases={'c': 'CENTER', 'l': 'LEFT', 'r': 'RIGHT'}):
    NONE = None
    LEFT = tkc.LEFT
    CENTER = tkc.CENTER
    RIGHT = tkc.RIGHT

    def as_anchor(self):
        return JUSTIFY_TO_ANCHOR.get(self.value)


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

    def as_sticky(self):
        return SIDE_STICKY_MAP.get(self.as_side())


class StyleState(MissingMixin, IntEnum):
    DEFAULT = 0
    DISABLED = 1
    INVALID = 2
    ACTIVE = 3


class ListBoxSelectMode(MissingMixin, Enum):
    BROWSE = tkc.BROWSE         #: Select 1 item; can drag mouse and selection will follow (tk default)
    SINGLE = tkc.SINGLE         #: Select 1 item; cannot drag mouse to move selection
    MULTIPLE = tkc.MULTIPLE     #: Select multiple items; each must be clicked individually
    EXTENDED = tkc.EXTENDED     #: Select multiple items; can drag mouse to select multiple items (lib default)
