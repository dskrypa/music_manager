"""
GUI styles / themes

:author: Doug Skrypa
"""

import logging
from functools import cached_property
from itertools import count
from tkinter.font import Font as _Font
from typing import Union, Optional, Literal

__all__ = ['Style', 'StateColors', 'Colors', 'State', 'Font']
log = logging.getLogger(__name__)
Font = Union[str, tuple[str, int]]
State = Literal['default', 'disabled', 'invalid']
Colors = Union['StateColors', dict[State, str], tuple[Optional[str], ...], str]


class Color:
    def __set_name__(self, owner, name):
        self.name = name

    def __get__(self, instance: 'StateColors', owner):
        if instance is None:
            return self
        elif (value := instance.__dict__[self.name]) is not None:
            return value
        elif '_' in instance.type:
            value = getattr(getattr(instance, instance.type.rsplit('_', 1)[1]), self.name)
        elif (parent := instance.style.parent) is not None:
            value = getattr(getattr(parent, instance.type), self.name)
        elif (style := Style.default) is not None:
            value = getattr(getattr(style, instance.type), self.name)
        return value

    def __set__(self, instance: 'StateColors', value: Optional[str]):
        instance.__dict__[self.name] = value


class StateColors:
    default = Color()
    disabled = Color()
    invalid = Color()

    def __init__(self, style: 'Style', type: str, default: str = None, disabled: str = None, invalid: str = None):  # noqa
        self.style = style
        self.type = type
        self.default = default
        self.disabled = disabled
        self.invalid = invalid

    def copy(self):
        data = self.__dict__
        return self.__class__(self.style, self.type, data['default'], data['disabled'], data['invalid'])

    @classmethod
    def init(cls, style: 'Style', type: str, colors: Colors = None):  # noqa
        if colors is None:
            return cls(style, type)
        elif isinstance(colors, cls):
            if colors.type != type:
                colors = colors.copy()
                colors.type = type
            return colors
        elif isinstance(colors, tuple):
            return cls(style, type, *colors)
        elif isinstance(colors, dict):
            return cls(style, type, **colors)
        elif isinstance(colors, str):
            return cls(style, type, default=colors)
        else:
            raise TypeError(f'Invalid type={colors.__class__.__name__!r} to initialize {cls.__name__}')


class Style:
    _count = count()
    _instances = {}
    default = None  # type: Optional[Style]

    def __init__(
        self,
        name: str = None,
        *,
        parent: Union[str, 'Style'] = None,
        font: Font = None,
        ttk_theme: str = None,
        border_width: int = None,
        insert_bg: str = None,
        text: Colors = None,
        bg: Colors = None,
        button_fg: Colors = None,
        button_bg: Colors = None,
        input_fg: Colors = None,
        input_bg: Colors = None,
    ):
        if name is None:
            name = f'{self.__class__.__name__}#{next(self._count)}'
        else:
            self._instances[name] = self
        self.parent = self.__class__[parent] if isinstance(parent, str) else parent
        self.name = name
        self._font = font
        self._ttk_theme = ttk_theme
        self._border_width = border_width
        self._insert_bg = insert_bg
        self.fg = self.text = StateColors.init(self, 'fg', text)
        self.bg = StateColors.init(self, 'bg', bg)
        self.button_fg = StateColors.init(self, 'button_fg', button_fg)
        self.button_bg = StateColors.init(self, 'button_bg', button_bg)
        self.input_fg = StateColors.init(self, 'input_fg', input_fg)
        self.input_bg = StateColors.init(self, 'input_bg', input_bg)

    def _get_value(self, attr: str):
        if (value := getattr(self, f'_{attr}')) is not None:
            return value
        elif self.parent is not None:
            return self.parent._get_value(attr)
        elif self.default is not None:
            return self.default._get_value(attr)
        return None

    @property
    def font(self) -> Font:
        return self._get_value('font')

    @property
    def ttk_theme(self):
        return self._get_value('ttk_theme')

    @property
    def border_width(self):
        return self._get_value('border_width')

    @property
    def insert_bg(self):
        return self._get_value('insert_bg')

    def __class_getitem__(cls, name: str) -> 'Style':
        return cls._instances[name]

    @classmethod
    def get(cls, name: Union[str, 'Style', None]) -> 'Style':
        if name is None:
            return cls.default
        elif isinstance(name, cls):
            return name
        return cls[name]  # noqa

    def __getitem__(self, type: str) -> StateColors:  # noqa
        try:
            value = getattr(self, type)
        except AttributeError:
            raise KeyError(type) from None
        if not isinstance(value, StateColors):
            raise KeyError(type)
        return value

    def make_default(self):
        Style.default = self

    @cached_property
    def char_width(self) -> int:
        return _Font(font=self.font).measure('A')

    @cached_property
    def char_height(self) -> int:
        return _Font(font=self.font).measure('linespace')

    def measure(self, text: str) -> int:
        return _Font(font=self.font).measure(text)

    def get_fg_bg(self, type: str, state: str = None) -> tuple[Optional[str], Optional[str]]:  # noqa
        fg, bg = f'{type}_fg', f'{type}_bg'
        state = state or 'default'
        return getattr(getattr(self, fg), state), getattr(getattr(self, bg), state)


Style('default', font=('Helvetica', 10), ttk_theme='default', border_width=1)
Style(
    'DarkGrey10', parent='default', text=('#cccdcf', '#000000', '#FFFFFF'), bg=('#1c1e23', '#a2a2a2', '#781F1F'),
    insert_bg='#FFFFFF', input_fg='#8b9fde', input_bg='#272a31', button_fg='#f5f5f6', button_bg='#2e3d5a',
).make_default()
