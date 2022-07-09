"""
GUI styles / themes

:author: Doug Skrypa
"""

from __future__ import annotations

# import logging
from collections import namedtuple
from enum import IntEnum
from itertools import count
from tkinter.font import Font as TkFont
from typing import TYPE_CHECKING, Union, Optional, Literal, Type, Mapping, Iterator, Any, Generic, TypeVar, overload

from .utils import ClearableCachedPropertyMixin, MissingMixin, Inheritable

if TYPE_CHECKING:
    from .typing import XY

__all__ = ['Style', 'StyleSpec']
# log = logging.getLogger(__name__)

StyleSpec = Union[str, 'Style', None]


class State(MissingMixin, IntEnum):
    DEFAULT = 0
    DISABLED = 1
    INVALID = 2


T_co = TypeVar('T_co', covariant=True)

StyleAttr = Literal['font', 'tk_font', 'fg', 'bg', 'border_width']
StateName = Literal['default', 'disabled', 'invalid']
StyleState = Union[State, StateName, Literal[0, 1, 2]]

OptStr = Optional[str]
_OptStrTuple = Union[tuple[OptStr], tuple[OptStr, OptStr], tuple[OptStr, OptStr, OptStr]]
OptStrVals = SV = Union[OptStr, Mapping[StyleState, OptStr], _OptStrTuple]

OptInt = Optional[int]
_OptIntTuple = Union[tuple[OptInt], tuple[OptInt, OptInt], tuple[OptInt, OptInt, OptInt]]
OptIntVals = IV = Union[OptInt, Mapping[StyleState, OptInt], _OptIntTuple]

Font = Union[str, tuple[str, int], None]
_FontValsTuple = Union[tuple[Font], tuple[Font, Font], tuple[Font, Font, Font]]
FontValues = FV = Union[Font, Mapping[StyleState, Font], _FontValsTuple]

StyleValue = Union[OptStr, OptInt, Font]
FinalValue = Union[StyleValue, TkFont]
RawStateValues = Union[OptStrVals, OptIntVals, FontValues]

_PartValsTuple = Union[tuple[FV], tuple[FV, SV], tuple[FV, SV, SV], tuple[FV, SV, SV, IV]]
PartValues = Union[FontValues, _PartValsTuple, Mapping[StyleState, StyleValue]]


StateValueTuple = namedtuple('StateValueTuple', ('default', 'disabled', 'invalid'))


class StateValue(Generic[T_co]):
    """Allows state-based component values to be accessed by name"""

    __slots__ = ('name',)

    def __set_name__(self, owner: Type[StateValues], name: StateName):
        self.name = name

    def __get__(self, instance: Optional[StateValues], owner: Type[StateValues]) -> Union[StateValue, Optional[T_co]]:
        if instance is None:
            return self
        return instance[self.name]

    def __set__(self, instance: StateValues, value: Optional[T_co]):
        instance[self.name] = value


class StateValues(Generic[T_co]):
    __slots__ = ('values', 'part', 'name')

    default = StateValue()
    disabled = StateValue()
    invalid = StateValue()

    def __init__(
        self,
        part: StylePart,
        name: str,
        default: Optional[T_co] = None,
        disabled: Optional[T_co] = None,
        invalid: Optional[T_co] = None,
    ):
        self.name = name
        self.part = part
        self.values = StateValueTuple(default, disabled, invalid)

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__}[{self.part.layer.name}.{self.name}: {self.values}]>'

    # region Overloads

    @classmethod
    @overload
    def new(cls, part: StylePart, name: str, values: FontValues) -> StateValues[Font]:
        ...

    @classmethod
    @overload
    def new(cls, part: StylePart, name: str, values: OptStrVals) -> StateValues[OptStr]:
        ...

    @classmethod
    @overload
    def new(cls, part: StylePart, name: str, values: OptIntVals) -> StateValues[OptInt]:
        ...

    # endregion

    @classmethod
    def new(
        cls, part: StylePart, name: str, values: Union[RawStateValues, StateValues[T_co]] = None
    ) -> StateValues[T_co]:
        if not values:
            return cls(part, name)
        elif isinstance(values, cls):
            return values.copy(part, name)
        elif isinstance(values, (str, int)):
            return cls(part, name, values)
        try:
            return cls(part, name, **values)
        except TypeError:
            pass
        try:
            return cls(part, name, *values)
        except TypeError:
            pass
        raise TypeError(f'Invalid type={values.__class__.__name__!r} to initialize {cls.__name__}')

    def copy(self: StateValues[T_co], part: StylePart = None, name: str = None) -> StateValues[T_co]:
        return self.__class__(part or self.part, name or self.name, *self.values)

    def __call__(self, state: StyleState = State.DEFAULT) -> Optional[T_co]:
        state = State(state)
        value = self.values[state]
        if not value and state != State.DEFAULT:
            return self.values[State.DEFAULT]
        return value

    def __getitem__(self, state: StyleState) -> Optional[T_co]:
        state = State(state)
        value = self.values[state]
        if not value and state != State.DEFAULT:
            return self.values[State.DEFAULT]
        return value

    def __setitem__(self, state: StyleState, value: Optional[T_co]):
        state = State(state)
        self.values = StateValues(*(value if i == state else v for i, v in enumerate(self.values)))

    def __iter__(self) -> Iterator[Optional[T_co]]:
        yield from self.values


class PartStateValues(Generic[T_co]):
    __slots__ = ('name', 'priv_name')

    def __set_name__(self, owner: Type[StylePart], name: str):
        self.name = name
        self.priv_name = f'_{name}'

    def get_values(self, style: Optional[Style], layer_name: str) -> Optional[StateValues[T_co]]:
        if layer := style.__dict__.get(layer_name):  # type: StylePart
            return getattr(layer, self.name)
        return None

    def get_parent_values(self, style: Optional[Style], layer_name: str) -> Optional[StateValues[T_co]]:
        while style:
            if state_values := self.get_values(style, layer_name):
                return state_values

            style = style.parent

        return None

    def __get__(
        self, instance: Optional[StylePart], owner: Type[StylePart]
    ) -> Union[PartStateValues, Optional[StateValues[T_co]]]:
        if instance is None:
            return self

        # print(f'{instance.style}.{instance.layer.name}.{self.name}...')
        if state_values := getattr(instance, self.priv_name):
            return state_values

        layer_name = instance.layer.name
        style = instance.style
        if state_values := self.get_parent_values(style.parent, layer_name):
            return state_values
        elif (default_style := Style.default_style) and default_style is not style:
            if state_values := self.get_values(default_style, layer_name):
                return state_values

        if layer_parent := instance.layer.parent:
            return getattr(getattr(style, layer_parent), self.name)
        elif not style.parent or style is default_style:
            state_values = StateValues(instance, self.name)
            setattr(instance, self.priv_name, state_values)
            return state_values

        return None

    def __set__(self, instance: StylePart, value: RawStateValues):
        if value is None:
            setattr(instance, self.priv_name, None)
        else:
            setattr(instance, self.priv_name, StateValues.new(instance, self.name, value))


class FontStateValues(PartStateValues):
    __slots__ = ()

    def __set__(self, instance: StylePart, value: FontValues):
        match value:  # noqa
            case None:
                setattr(instance, self.priv_name, None)
            case (str(_name), int(_size)):
                setattr(instance, self.priv_name, StateValues(instance, self.name, value))
            case _:
                setattr(instance, self.priv_name, StateValues.new(instance, self.name, value))

        try:
            del instance._tk_font
        except AttributeError:
            pass


class StylePart:
    __slots__ = ('style', 'layer', '_tk_font', '_font', '_fg', '_bg', '_border_width')

    font: StateValues[Font] = FontStateValues()
    fg: StateValues[OptStr] = PartStateValues()
    bg: StateValues[OptStr] = PartStateValues()
    border_width: StateValues[OptInt] = PartStateValues()

    def __init__(
        self,
        style: Style,
        layer: StyleLayer,
        font: FontValues = None,
        fg: OptStrVals = None,
        bg: OptStrVals = None,
        border_width: OptIntVals = None,
    ):
        self.style = style
        self.layer = layer
        self.font = font  # noqa
        self.fg = fg  # noqa
        self.bg = bg  # noqa
        self.border_width = border_width  # noqa

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__}[{self.style.name}: {self.layer.name}]>'

    @classmethod
    def new(cls, style: Style, layer: StyleLayer, values: PartValues = None) -> StylePart:
        if not values:
            return cls(style, layer)
        elif isinstance(values, (str, int)):
            return cls(style, layer, values)
        try:
            return cls(style, layer, **values)
        except TypeError:
            pass
        try:
            return cls(style, layer, *values)
        except TypeError:
            pass
        raise TypeError(f'Invalid type={values.__class__.__name__!r} to initialize {cls.__name__}')

    @property
    def tk_font(self) -> StateValues[Optional[TkFont]]:
        try:
            return self._tk_font
        except AttributeError:
            parts = (TkFont(font=font) if font else None for font in self.font)
            self._tk_font = tk_font = StateValues(self, 'tk_font', *parts)  # noqa
            return tk_font

    def as_dict(self) -> dict[str, StateValues]:
        parts = ((attr[1:], getattr(self, attr)) for attr in self.__slots__[3:])
        return {key: getattr(val, 'values', None) for key, val in parts}


class StyleLayer:
    __slots__ = ('name', 'parent')

    def __init__(self, parent: str = None):
        self.parent = parent

    def __set_name__(self, owner: Type[Style], name: str):
        self.name = name
        owner._layers.add(name)

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__}[{self.name}]>'

    def get_parent_part(self, style: Optional[Style]) -> Optional[StylePart]:
        while style:
            if part := style.__dict__.get(self.name):
                return part

            style = style.parent

        return None

    def __get__(self, instance: Optional[Style], owner: Type[Style]) -> Union[StyleLayer, StylePart, None]:
        if instance is None:
            return self
        elif part := self.get_parent_part(instance):
            return part
        elif (default := owner.default_style) and default is not instance:
            if part := default.__dict__.get(self.name):
                return part

        if not instance.parent or not default or instance is default:
            instance.__dict__[self.name] = part = StylePart(instance, self)
            return part

        return None

    def __set__(self, instance: Style, value: PartValues):
        instance.__dict__[self.name] = StylePart.new(instance, self, value)


Layer = Literal['base', 'insert', 'hover', 'focus', 'tooltip', 'image', 'button', 'input', 'table', 'table_header']


class Style(ClearableCachedPropertyMixin):
    _count = count()
    _layers: set[str] = set()
    _instances: dict[str, Style] = {}
    default_style: Optional[Style] = None

    name: str
    parent: Optional[Style]

    ttk_theme: Optional[str] = Inheritable()

    base = StyleLayer()
    insert = StyleLayer()
    hover = StyleLayer()
    focus = StyleLayer()
    tooltip = StyleLayer('base')
    image = StyleLayer('base')
    button = StyleLayer('base')
    input = StyleLayer('base')
    table = StyleLayer('base')
    table_header = StyleLayer('table')

    def __init__(self, name: str = None, *, parent: Union[str, Style] = None, ttk_theme: str = None, **kwargs):
        if not name:  # Anonymous styles won't be stored
            name = f'{self.__class__.__name__}#{next(self._count)}'
        else:
            self._instances[name] = self

        self.name = name
        self.parent = self._instances.get(parent, parent)
        self.ttk_theme = ttk_theme
        self._configure(kwargs)

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__}[{self.name!r}, parent={self.parent.name if self.parent else None}]>'

    def _configure(self, kwargs: dict[str, Any]):
        attrs = {'font': 'font', 'fg': 'fg', 'bg': 'bg', 'border_width': 'border_width', 'text': 'fg'}

        layers = {}

        for key, val in kwargs.items():
            if key in self._layers:
                # log.info(f'{self}: Full layer config provided: {key}={val!r}', extra={'color': 11})
                setattr(self, key, val)
            elif dst_key := attrs.get(key):
                layers.setdefault('base', {})[dst_key] = val
            else:
                for delim in ('_', '.'):
                    try:
                        layer, attr = key.rsplit(delim, 1)
                    except ValueError:
                        continue
                    if layer in self._layers and (dst_key := attrs.get(attr)):
                        layers.setdefault(layer, {})[dst_key] = val
                        break
                else:
                    raise KeyError(f'Invalid style option: {key!r}')

        # log.info(f'{self}: Built layers: {layers!r}', extra={'color': 11})

        for name, layer in layers.items():
            setattr(self, name, layer)

    @classmethod
    def get_style(cls, style: StyleSpec) -> Style:
        if not style:
            return cls.default_style
        elif isinstance(style, cls):
            return style
        return cls._instances[style]

    def __class_getitem__(cls, name: str) -> Style:
        return cls._instances[name]

    def as_dict(self) -> dict[str, Union[str, None, dict[str, StateValues]]]:
        get = self.__dict__.get
        style = {'name': self.name, 'parent': self.parent.name if self.parent else None, 'ttk_theme': get('ttk_theme')}
        for name in self._layers:
            if layer := get(name):
                style[name] = layer.as_dict()
            else:
                style[name] = None
        return style

    def make_default(self):
        self.__class__.default_style = self

    def get(
        self, *attrs: StyleAttr, layer: Layer = 'base', state: StyleState = State.DEFAULT, **kwattrs: str
    ) -> dict[str, FinalValue]:
        found = {}

        if layer != 'base' and (layer_obj := getattr(self, layer)):
            layers = (layer_obj, self.base)
        else:
            layers = (self.base,)

        for attr in attrs:
            kwattrs.setdefault(attr, attr)

        for attr, key in kwattrs.items():
            for layer in layers:
                if value := getattr(layer, attr)[state]:
                    found[key] = value
                    break
            else:
                found[key] = None

        return found

    # region Font Methods

    def char_height(self, layer: Layer = 'base', state: StyleState = State.DEFAULT) -> int:
        tk_font: TkFont = getattr(self, layer).tk_font[state]
        return tk_font.metrics('linespace')

    def char_width(self, layer: Layer = 'base', state: StyleState = State.DEFAULT) -> int:
        tk_font: TkFont = getattr(self, layer).tk_font[state]
        return tk_font.measure('A')

    def measure(self, text: str, layer: Layer = 'base', state: StyleState = State.DEFAULT) -> int:
        tk_font: TkFont = getattr(self, layer).tk_font[state]
        return tk_font.measure(text)

    def text_size(self, text: str, layer: Layer = 'base', state: StyleState = State.DEFAULT) -> XY:
        tk_font: TkFont = getattr(self, layer).tk_font[state]
        width = tk_font.measure(text)
        height = tk_font.metrics('linespace')
        return width, height

    # endregion


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
