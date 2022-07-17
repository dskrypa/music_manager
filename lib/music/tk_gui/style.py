"""
GUI styles / themes

:author: Doug Skrypa
"""

from __future__ import annotations

# import logging
from collections import namedtuple
from itertools import count
from tkinter.font import Font as TkFont
from tkinter.ttk import Style as TtkStyle
from typing import TYPE_CHECKING, Union, Optional, Literal, Type, Mapping, Iterator, Any, Generic, TypeVar, Iterable
from typing import overload

from .enums import StyleState
from .utils import ClearableCachedPropertyMixin

if TYPE_CHECKING:
    from .typing import XY

__all__ = ['Style', 'StyleSpec']
# log = logging.getLogger(__name__)

StyleOptions = Mapping[str, Any]
StyleSpec = Union[str, 'Style', StyleOptions, tuple[str, StyleOptions], None]

T = TypeVar('T')
T_co = TypeVar('T_co', covariant=True)

StyleAttr = Literal[
    'font', 'tk_font', 'fg', 'bg', 'border_width', 'relief',
    'frame_color', 'trough_color', 'arrow_color', 'arrow_width', 'bar_width',
]
Relief = Optional[Literal['raised', 'sunken', 'flat', 'ridge', 'groove', 'solid']]
StateName = Literal['default', 'disabled', 'invalid']
StyleStateVal = Union[StyleState, StateName, Literal[0, 1, 2]]

OptStr = Optional[str]
_OptStrTuple = Union[tuple[OptStr], tuple[OptStr, OptStr], tuple[OptStr, OptStr, OptStr]]
OptStrVals = Union[OptStr, Mapping[StyleStateVal, OptStr], _OptStrTuple]

OptInt = Optional[int]
_OptIntTuple = Union[tuple[OptInt], tuple[OptInt, OptInt], tuple[OptInt, OptInt, OptInt]]
OptIntVals = Union[OptInt, Mapping[StyleStateVal, OptInt], _OptIntTuple]

Font = Union[str, tuple[str, int], None]
_FontValsTuple = Union[tuple[Font], tuple[Font, Font], tuple[Font, Font, Font]]
FontValues = Union[Font, Mapping[StyleStateVal, Font], _FontValsTuple]

StyleValue = Union[OptStr, OptInt, Font]
FinalValue = Union[StyleValue, TkFont]
RawStateValues = Union[OptStrVals, OptIntVals, FontValues]

LayerValues = Union[FontValues, Mapping[StyleStateVal, StyleValue]]

# region State Values

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
    __slots__ = ('values', 'layer', 'name')

    default = StateValue()
    disabled = StateValue()
    invalid = StateValue()

    def __init__(
        self,
        layer: StyleLayer,
        name: str,
        default: Optional[T_co] = None,
        disabled: Optional[T_co] = None,
        invalid: Optional[T_co] = None,
    ):
        self.name = name
        self.layer = layer
        self.values = StateValueTuple(default, disabled, invalid)

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__}[{self.layer.prop.name}.{self.name}: {self.values}]>'

    # region Overloads

    @classmethod
    @overload
    def new(cls, layer: StyleLayer, name: str, values: FontValues) -> StateValues[Font]:
        ...

    @classmethod
    @overload
    def new(cls, layer: StyleLayer, name: str, values: OptStrVals) -> StateValues[OptStr]:
        ...

    @classmethod
    @overload
    def new(cls, layer: StyleLayer, name: str, values: OptIntVals) -> StateValues[OptInt]:
        ...

    # endregion

    @classmethod
    def new(
        cls, layer: StyleLayer, name: str, values: Union[RawStateValues, StateValues[T_co]] = None
    ) -> StateValues[T_co]:
        if not values:
            return cls(layer, name)
        elif isinstance(values, cls):
            return values.copy(layer, name)
        elif isinstance(values, (str, int)):
            return cls(layer, name, values)
        try:
            return cls(layer, name, **values)
        except TypeError:
            pass
        try:
            return cls(layer, name, *values)
        except TypeError:
            pass
        raise TypeError(f'Invalid type={values.__class__.__name__!r} to initialize {cls.__name__}')

    def copy(self: StateValues[T_co], layer: StyleLayer = None, name: str = None) -> StateValues[T_co]:
        return self.__class__(layer or self.layer, name or self.name, *self.values)

    def __call__(self, state: StyleStateVal = StyleState.DEFAULT) -> Optional[T_co]:
        state = StyleState(state)
        value = self.values[state]
        if not value and state != StyleState.DEFAULT:
            return self.values[StyleState.DEFAULT]
        return value

    def __getitem__(self, state: StyleStateVal) -> Optional[T_co]:
        state = StyleState(state)
        value = self.values[state]
        if not value and state != StyleState.DEFAULT:
            return self.values[StyleState.DEFAULT]
        return value

    def __setitem__(self, state: StyleStateVal, value: Optional[T_co]):
        state = StyleState(state)
        self.values = StateValues(*(value if i == state else v for i, v in enumerate(self.values)))

    def __iter__(self) -> Iterator[Optional[T_co]]:
        yield from self.values


class LayerStateValues(Generic[T_co]):
    __slots__ = ('name',)

    def __set_name__(self, owner: Type[StyleLayer], name: str):
        self.name = name
        owner._fields.add(name)

    def get_values(self, style: Optional[Style], layer_name: str) -> Optional[StateValues[T_co]]:
        if layer := style.__dict__.get(layer_name):  # type: StyleLayer
            return getattr(layer, self.name)
        return None

    def get_parent_values(self, style: Optional[Style], layer_name: str) -> Optional[StateValues[T_co]]:
        while style:
            if state_values := self.get_values(style, layer_name):
                return state_values

            style = style.parent

        return None

    def __get__(
        self, instance: Optional[StyleLayer], owner: Type[StyleLayer]
    ) -> Union[LayerStateValues, Optional[StateValues[T_co]]]:
        if instance is None:
            return self

        # print(f'{instance.style}.{instance.layer.name}.{self.name}...')
        if state_values := instance.__dict__.get(self.name):
            return state_values

        layer_name = instance.prop.name
        style = instance.style
        if state_values := self.get_parent_values(style.parent, layer_name):
            return state_values
        elif (default_style := Style.default_style) and style not in (default_style, default_style.parent):
            if state_values := self.get_values(default_style, layer_name):
                return state_values

        if layer_parent := instance.prop.parent:
            return getattr(getattr(style, layer_parent), self.name)
        elif not style.parent or style is default_style:
            instance.__dict__[self.name] = state_values = StateValues(instance, self.name)
            return state_values

        return None

    def __set__(self, instance: StyleLayer, value: RawStateValues):
        if value is None:
            instance.__dict__[self.name] = None
        else:
            instance.__dict__[self.name] = StateValues.new(instance, self.name, value)


class FontStateValues(LayerStateValues):
    __slots__ = ()

    def __set__(self, instance: StyleLayer, value: FontValues):
        match value:  # noqa
            case None:
                instance.__dict__[self.name] = None
            case (str(_name), int(_size)):
                instance.__dict__[self.name] = StateValues(instance, self.name, value)
            case _:
                instance.__dict__[self.name] = StateValues.new(instance, self.name, value)

        try:
            del instance._tk_font
        except AttributeError:
            pass


# endregion


class StyleLayer:
    _fields: set[str] = set()
    font: StateValues[Font] = FontStateValues()             # Font to use
    fg: StateValues[OptStr] = LayerStateValues()            # Foreground / text color
    bg: StateValues[OptStr] = LayerStateValues()            # Background color
    border_width: StateValues[OptInt] = LayerStateValues()  # Border width
    # border_color: StateValues[OptStr] = LayerStateValues()  # Border color
    relief: StateValues[OptStr] = LayerStateValues()        # Visually differentiate the edges of some elements
    # Scroll bar options
    frame_color: StateValues[OptStr] = LayerStateValues()   # Frame color
    trough_color: StateValues[OptStr] = LayerStateValues()  # Trough (area where scroll bars can travel) color
    arrow_color: StateValues[OptStr] = LayerStateValues()   # Color for the arrows at either end of scroll bars
    arrow_width: StateValues[OptInt] = LayerStateValues()   # Width of scroll bar arrows in px
    bar_width: StateValues[OptInt] = LayerStateValues()     # Width of scroll bars in px

    @overload
    def __init__(
        self,
        style: Style,
        prop: StyleLayerProperty,
        *,
        font: FontValues = None,
        fg: OptStrVals = None,
        bg: OptStrVals = None,
        border_width: OptIntVals = None,
        # border_color: OptStrVals = None,
        frame_color: OptStrVals = None,
        trough_color: OptStrVals = None,
        arrow_color: OptStrVals = None,
        arrow_width: OptIntVals = None,
        bar_width: OptIntVals = None,
        relief: OptStrVals = None,
    ):
        ...

    def __init__(self, style: Style, prop: StyleLayerProperty, **kwargs):
        self.style = style
        self.prop = prop
        bad = {}
        for key, val in kwargs.items():
            if key in self._fields:
                setattr(self, key, val)
            else:
                bad[key] = val
        if bad:
            raise ValueError(f'Invalid style layer options: {bad}')

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__}[{self.style.name}: {self.prop.name}]>'

    @classmethod
    def new(cls, style: Style, layer: StyleLayerProperty, values: LayerValues = None) -> StyleLayer:
        if not values:
            return cls(style, layer)
        try:
            return cls(style, layer, **values)
        except TypeError:
            pass
        raise TypeError(f'Invalid type={values.__class__.__name__!r} to initialize {cls.__name__}')

    @property
    def tk_font(self) -> StateValues[Optional[TkFont]]:
        try:
            return self._tk_font  # noqa
        except AttributeError:
            parts = (TkFont(font=font) if font else None for font in self.font)
            self._tk_font = tk_font = StateValues(self, 'tk_font', *parts)  # noqa
            return tk_font

    def as_dict(self) -> dict[str, StateValues]:
        return {key: getattr(val, 'values', None) for key, val in self.__dict__.items() if key in self._fields}


class StyleProperty(Generic[T]):
    __slots__ = ('name', 'default')

    def __init__(self, default: Optional[T] = None):
        self.default = default

    def __set_name__(self, owner: Type[Style], name: str):
        self.name = name

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__}[{self.name}]>'

    def get_parent_part(self, style: Optional[Style]) -> Optional[T]:
        while style:
            if part := style.__dict__.get(self.name):
                return part

            style = style.parent

        return None

    def __get__(self, instance: Optional[Style], owner: Type[Style]) -> Union[StyleProperty, T, None]:
        if instance is None:
            return self
        elif part := self.get_parent_part(instance):
            return part
        elif (default_style := owner.default_style) and default_style is not instance:
            if part := default_style.__dict__.get(self.name):
                return part
        return self.default

    def __set__(self, instance: Style, value: T):
        instance.__dict__[self.name] = value

    def __delete__(self, instance: Style):
        del instance.__dict__[self.name]


class StyleLayerProperty(StyleProperty[StyleLayer]):
    __slots__ = ('parent',)

    def __init__(self, parent: str = None):
        super().__init__(None)
        self.parent = parent

    def __set_name__(self, owner: Type[Style], name: str):
        self.name = name
        owner._layers.add(name)

    def __get__(self, instance: Optional[Style], owner: Type[Style]) -> Union[StyleLayerProperty, StyleLayer, None]:
        if instance is None:
            return self
        elif part := super().__get__(instance, owner):
            return part
        elif not instance.parent or not (default := owner.default_style) or instance is default:  # noqa
            instance.__dict__[self.name] = part = StyleLayer(instance, self)
            return part

        return None

    def __set__(self, instance: Style, value: LayerValues):
        instance.__dict__[self.name] = StyleLayer.new(instance, self, value)


Layer = Literal[
    'base', 'insert', 'hover', 'focus', 'scroll', 'radio', 'checkbox', 'frame',
    'tooltip', 'image', 'button', 'text', 'link', 'selected', 'input', 'table', 'table_header', 'table_alt',
]


class Style(ClearableCachedPropertyMixin):
    _count = count()
    _ttk_count = count()
    _layers: set[str] = set()
    _instances: dict[str, Style] = {}
    default_style: Optional[Style] = None

    name: str
    parent: Optional[Style]

    ttk_theme: Optional[str] = StyleProperty()

    base = StyleLayerProperty()
    insert = StyleLayerProperty()
    hover = StyleLayerProperty()
    focus = StyleLayerProperty()
    scroll = StyleLayerProperty()
    tooltip = StyleLayerProperty('base')
    image = StyleLayerProperty('base')
    button = StyleLayerProperty('base')
    text = StyleLayerProperty('base')
    link = StyleLayerProperty('text')               # Hyperlinks
    selected = StyleLayerProperty('base')           # Selected text / radio buttons / etc
    input = StyleLayerProperty('text')
    table = StyleLayerProperty('base')              # Table elements
    table_header = StyleLayerProperty('table')      # Table headers
    table_alt = StyleLayerProperty('table')         # Alternate / even rows in tables
    radio = StyleLayerProperty('base')
    checkbox = StyleLayerProperty('base')
    frame = StyleLayerProperty('base')

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

    # region Configuration / Init

    def _configure(self, kwargs: StyleOptions):
        layers = {}
        for key, val in kwargs.items():
            if key in self._layers:
                # log.info(f'{self}: Full layer config provided: {key}={val!r}', extra={'color': 11})
                setattr(self, key, val)
            elif key in StyleLayer._fields:
                layers.setdefault('base', {})[key] = val
            else:
                layer, attr = self._split_config_key(key)
                layers.setdefault(layer, {})[attr] = val

        # log.info(f'{self}: Built layers: {layers!r}', extra={'color': 11})
        for name, layer in layers.items():
            setattr(self, name, layer)

    def _split_config_key(self, key: str) -> tuple[str, str]:
        for delim in '_.':
            try:
                layer, attr = key.split(delim, 1)
            except ValueError:
                continue

            if layer in self._layers and attr in StyleLayer._fields:
                return layer, attr

        for layer in self._compound_layer_names():
            n = len(layer) + 1
            if key.startswith(layer) and len(key) > n and key[n - 1] in '_.':
                if (attr := key[n:]) in StyleLayer._fields:
                    return layer, attr

        raise KeyError(f'Invalid style option: {key!r}')

    @classmethod
    def _compound_layer_names(cls) -> set[str]:
        try:
            return cls.__compound_layer_names  # noqa
        except AttributeError:
            cls.__compound_layer_names = names = {name for name in cls._layers if '_' in name}
            return names

    @classmethod
    def get_style(cls, style: StyleSpec) -> Style:
        if not style:
            return cls.default_style
        elif isinstance(style, cls):
            return style
        elif isinstance(style, str):
            return cls._instances[style]
        try:
            return cls(**style)
        except TypeError:
            pass
        try:
            name, kwargs = style
        except (ValueError, TypeError):
            raise TypeError(f'Invalid {style=}') from None
        return cls(name, **kwargs)

    def __class_getitem__(cls, name: str) -> Style:
        return cls._instances[name]

    def make_default(self):
        self.__class__.default_style = self

    # endregion

    def as_dict(self) -> dict[str, Union[str, None, dict[str, StateValues]]]:
        get = self.__dict__.get
        style = {'name': self.name, 'parent': self.parent.name if self.parent else None, 'ttk_theme': get('ttk_theme')}
        for name in self._layers:
            if layer := get(name):
                style[name] = layer.as_dict()
            else:
                style[name] = None
        return style

    def get_map(
        self,
        layer: Layer = 'base',
        state: StyleStateVal = StyleState.DEFAULT,
        attrs: Iterable[StyleAttr] = None,  # Note: PyCharm doesn't handle this Literal well
        include_none: bool = False,
        **dst_src_map
    ) -> dict[str, FinalValue]:
        layer: StyleLayer = getattr(self, layer)
        if attrs is not None:
            dst_src_map.update((a, a) for a in attrs)

        found = {}
        for dst, src in dst_src_map.items():
            value = getattr(layer, src)[state]
            if include_none or value is not None:
                found[dst] = value

        return found

    def make_ttk_style(self, name_suffix: str) -> tuple[str, TtkStyle]:
        name = f'{next(self._ttk_count)}__{name_suffix}'
        ttk_style = TtkStyle()
        ttk_style.theme_use(self.ttk_theme)
        return name, ttk_style

    # region Font Methods

    def char_height(self, layer: Layer = 'base', state: StyleStateVal = StyleState.DEFAULT) -> int:
        tk_font: TkFont = getattr(self, layer).tk_font[state]
        return tk_font.metrics('linespace')

    def char_width(self, layer: Layer = 'base', state: StyleStateVal = StyleState.DEFAULT) -> int:
        tk_font: TkFont = getattr(self, layer).tk_font[state]
        return tk_font.measure('A')

    def measure(self, text: str, layer: Layer = 'base', state: StyleStateVal = StyleState.DEFAULT) -> int:
        tk_font: TkFont = getattr(self, layer).tk_font[state]
        return tk_font.measure(text)

    def text_size(self, text: str, layer: Layer = 'base', state: StyleStateVal = StyleState.DEFAULT) -> XY:
        tk_font: TkFont = getattr(self, layer).tk_font[state]
        width = tk_font.measure(text)
        height = tk_font.metrics('linespace')
        return width, height

    # endregion


Style('default', font=('Helvetica', 10), ttk_theme='default', border_width=1)
Style(
    'DarkGrey10',
    parent='default',
    fg=('#cccdcf', '#000000', '#FFFFFF'),
    bg=('#1c1e23', '#a2a2a2', '#781F1F'),
    link_fg='#3a78f2',
    selected_fg=('#1c1e23', '#a2a2a2', '#781F1F'),  # Inverse of non-selected
    selected_bg=('#cccdcf', '#000000', '#FFFFFF'),
    insert_bg='#FFFFFF',
    input_fg='#8b9fde',
    input_bg='#272a31',
    button_fg='#f5f5f6',
    button_bg='#2e3d5a',
    tooltip_fg='#000000',
    tooltip_bg='#ffffe0',
    table_alt_fg='#8b9fde',
    table_alt_bg='#272a31',
).make_default()
