"""
Configuration options for Command behavior.

:author: Doug Skrypa
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Union, Callable, Type, TypeVar, Generic, overload

from .enums import CollabMode

if TYPE_CHECKING:
    from ..typing import Bool, StrOrStrs

__all__ = ['UpdateConfig']

CV = TypeVar('CV')
DV = TypeVar('DV')
ConfigValue = Union[CV, DV]


class ConfigItem(Generic[CV, DV]):
    __slots__ = ('default', 'type', 'name')

    def __init__(self, default: DV, type: Callable[[Any], CV] = None):  # noqa
        self.default = default
        self.type = type

    def __set_name__(self, owner: Type[UpdateConfig], name: str):
        self.name = name
        owner.FIELDS.add(name)

    @overload
    def __get__(self, instance: None, owner: Type[UpdateConfig]) -> ConfigItem[CV, DV]:
        ...

    @overload
    def __get__(self, instance: UpdateConfig, owner: Type[UpdateConfig]) -> ConfigValue:
        ...

    def __get__(self, instance, owner):
        if instance is None:
            return self
        try:
            return instance.__dict__[self.name]
        except KeyError:
            return self.default

    def __set__(self, instance: UpdateConfig, value: ConfigValue):
        if self.type is not None:
            value = self.type(value)
        instance.__dict__[self.name] = value

    def __delete__(self, instance: UpdateConfig):
        try:
            del instance.__dict__[self.name]
        except KeyError as e:
            raise AttributeError(f'No {self.name!r} config was stored for {instance}') from e

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__}({self.default!r}, type={self.type!r})>'


def _normalize_sites(sites: StrOrStrs) -> set[str]:
    if not sites:
        return set()
    elif isinstance(sites, str):
        return {sites}
    else:
        return set(sites)


class UpdateConfig:
    """Configuration options for matching / updating via wiki."""

    FIELDS = set()

    # region Artist Options

    soloist: Bool = ConfigItem(False, bool)
    collab_mode: CollabMode = ConfigItem(CollabMode.ARTIST, CollabMode.get)

    # endregion

    # region Album Options

    hide_edition: Bool = ConfigItem(False, bool)
    update_cover: Bool = ConfigItem(False, bool)
    add_genre: Bool = ConfigItem(True, bool)

    # endregion

    # region General Options

    add_bpm: Bool = ConfigItem(False, bool)
    artist_only: Bool = ConfigItem(False, bool)
    title_case: Bool = ConfigItem(False, bool)
    no_album_move: Bool = ConfigItem(False, bool)

    # endregion

    # region Site Options

    artist_sites: StrOrStrs = ConfigItem((), _normalize_sites)
    album_sites: StrOrStrs = ConfigItem((), _normalize_sites)

    # endregion

    @overload
    def __init__(
        self,
        soloist: Bool = False,
        collab_mode: CollabMode | str = CollabMode.ARTIST,
        hide_edition: Bool = False,
        update_cover: Bool = False,
        add_genre: Bool = True,
        add_bpm: Bool = False,
        artist_only: Bool = False,
        title_case: Bool = False,
        no_album_move: Bool = False,
        artist_sites: StrOrStrs = None,
        album_sites: StrOrStrs = None,
    ):
        ...

    def __init__(self, **kwargs):
        bad = {}
        for key, val in kwargs.items():
            if key in self.FIELDS:
                setattr(self, key, val)
            else:
                bad[key] = val
        if bad:
            raise ValueError(f'Invalid configuration - unsupported options: {", ".join(sorted(bad))}')

    def __repr__(self) -> str:
        settings = ', '.join(f'{k}={v!r}' for k, v in self.as_dict(False).items())
        cfg_str = f', {settings}' if settings else ''
        return f'<{self.__class__.__name__}({cfg_str})>'

    def as_dict(self, full: Bool = True) -> dict[str, Any]:
        """Return a dict representing the configured options."""
        if full:
            return {key: getattr(self, key) for key in self.FIELDS}
        return {key: val for key, val in self.__dict__.items() if key in self.FIELDS}
