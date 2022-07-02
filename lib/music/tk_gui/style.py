"""
GUI styles / themes

:author: Doug Skrypa
"""

from __future__ import annotations

# import logging
from functools import cached_property
from itertools import count
from tkinter.font import Font as _Font
from typing import Union, Optional, Literal, Type, Mapping, Sequence, Iterator, overload

__all__ = ['Style', 'StateColors', 'Colors', 'State', 'Font', 'StyleSpec']
# log = logging.getLogger(__name__)

Font = Union[str, tuple[str, int]]
State = Literal['default', 'disabled', 'invalid']
Colors = Union['StateColors', dict[State, str], tuple[Optional[str], ...], str]
StyleSpec = Union[str, 'Style', None]


class _NamedDescriptor:
    __slots__ = ('name',)

    def __set_name__(self, owner, name: str):
        self.name = name

    def __delete__(self, instance):
        try:
            del instance.__dict__[self.name]
        except KeyError as e:
            msg = f'{instance.__class__.__name__} object has no directly assigned value for {self.name!r}'
            raise AttributeError(msg) from e


class Color(_NamedDescriptor):
    __slots__ = ()

    def __get__(self, instance: Optional[StateColors], owner: Type[StateColors]):
        if instance is None:
            return self

        state = self.name
        for state_colors in self._iter_state_colors(instance):
            state_color_map = state_colors.__dict__
            if value := state_color_map[state]:
                return value
            elif state != 'default' and (value := state_color_map['default']):
                return value

        inst_type = instance.type  # <element type>_(fg|bg)
        try:
            _, base_type = inst_type.rsplit('_', 1)  # fg / bg
        except ValueError:
            return None
        else:
            return getattr(getattr(instance.style, base_type), state)

    @classmethod
    def _iter_state_colors(cls, state_colors: StateColors) -> Iterator[StateColors]:
        yield state_colors
        attr = state_colors.type
        for style in sro(state_colors.style.parent):
            if attr in style.__dict__:
                yield getattr(style, attr)

    def __set__(self, instance: StateColors, value: Optional[str]):
        instance.__dict__[self.name] = value


class StateColors:
    default = Color()
    disabled = Color()
    invalid = Color()

    def __init__(self, style: Style, type: str, default: str = None, disabled: str = None, invalid: str = None):  # noqa
        self.style = style
        self.type = type
        self.default = default
        self.disabled = disabled
        self.invalid = invalid

    def copy(self):
        data = self.__dict__
        return self.__class__(self.style, self.type, data['default'], data['disabled'], data['invalid'])

    @classmethod
    def init(cls, style: Style, type: str, colors: Colors = None):  # noqa
        if not colors:
            return cls(style, type)
        elif isinstance(colors, cls):
            if colors.type != type:
                colors = colors.copy()
                colors.type = type
            return colors
        elif isinstance(colors, str):
            return cls(style, type, default=colors)
        elif isinstance(colors, Mapping):
            return cls(style, type, **colors)
        elif isinstance(colors, Sequence):
            return cls(style, type, *colors)
        else:
            raise TypeError(f'Invalid type={colors.__class__.__name__!r} to initialize {cls.__name__}')


class StyleOption(_NamedDescriptor):
    __slots__ = ()

    def __set_name__(self, owner: Type[Style], name: str):
        self.name = name
        owner._fields.add(name)

    def __get__(self, instance: Optional[Style], owner: Type[Style]):
        if instance is None:
            return self
        return self.get_value(instance, owner)

    def get_value(self, instance: Optional[Style], owner: Type[Style]):
        for style in sro(instance):
            try:
                return style.__dict__[self.name]
            except KeyError:
                pass

        try:
            _, base_name = self.name.rsplit('_', 1)
        except ValueError:
            pass
        else:
            if base_name in owner._fields:
                return getattr(instance, base_name)

        return None

    def __set__(self, instance: Style, value):
        if value is None:
            instance.__dict__.pop(self.name, None)
        else:
            instance.__dict__[self.name] = value


class StatefulColor(StyleOption):
    __slots__ = ()

    def __get__(self, instance: Optional[Style], owner: Type[Style]) -> Union[StatefulColor, StateColors]:
        if instance is None:
            return self

        value = self.get_value(instance, owner)
        if not value:
            instance.__dict__[self.name] = value = StateColors.init(instance, self.name)
        return value

    def __set__(self, instance: Style, value: Optional[Colors]):
        if value is None:
            instance.__dict__.pop(self.name, None)
        else:
            instance.__dict__[self.name] = StateColors.init(instance, self.name, value)


def sro(style: Optional[Style]) -> Iterator[Style]:
    """Style resolution order"""
    while style:
        yield style
        style = style.parent

    if default := Style.default:
        yield default


class Style:
    _fields: set[str] = set()
    _count = count()
    _instances: dict[str, Style] = {}
    default: Optional[Style] = None

    name: str
    parent: Optional[Style]

    font: Optional[Font] = StyleOption()
    tooltip_font: Optional[Font] = StyleOption()
    ttk_theme: Optional[str] = StyleOption()
    border_width: Optional[int] = StyleOption()
    insert_bg: Optional[str] = StyleOption()

    fg = StatefulColor()
    bg = StatefulColor()
    text = fg
    button_fg = StatefulColor()
    button_bg = StatefulColor()
    input_fg = StatefulColor()
    input_bg = StatefulColor()
    tooltip_fg = StatefulColor()
    tooltip_bg = StatefulColor()

    @overload
    def __init__(
        self,
        name: str = None,
        *,
        parent: Union[str, Style] = None,
        font: Font = None,
        tooltip_font: Font = None,
        ttk_theme: str = None,
        border_width: int = None,
        insert_bg: str = None,
        text: Colors = None,
        bg: Colors = None,
        button_fg: Colors = None,
        button_bg: Colors = None,
        input_fg: Colors = None,
        input_bg: Colors = None,
        tooltip_fg: Colors = None,
        tooltip_bg: Colors = None,
    ):
        ...

    def __init__(self, name: str = None, *, parent: Union[str, Style] = None, **kwargs):
        if not name:  # Anonymous styles won't be stored
            name = f'{self.__class__.__name__}#{next(self._count)}'
        else:
            self._instances[name] = self
        self.parent = self._instances.get(parent, parent)
        self.name = name

        bad = {}
        for key, val in kwargs.items():
            if key in self._fields:
                setattr(self, key, val)
            else:
                bad[key] = val
        if bad:
            bad_str = ', '.join(sorted(bad))
            raise ValueError(f'Invalid {self.__class__.__name__} options - unsupported options: {bad_str}')

    def __class_getitem__(cls, name: str) -> Style:
        return cls._instances[name]

    @classmethod
    def get(cls, name: Union[str, Style, None]) -> Style:
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
    'DarkGrey10',
    parent='default',
    text=('#cccdcf', '#000000', '#FFFFFF'),
    bg=('#1c1e23', '#a2a2a2', '#781F1F'),
    insert_bg='#FFFFFF',
    input_fg='#8b9fde',
    input_bg='#272a31',
    button_fg='#f5f5f6',
    button_bg='#2e3d5a',
    tooltip_bg='#ffffe0',
).make_default()
