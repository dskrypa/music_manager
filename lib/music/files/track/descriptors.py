"""
:author: Doug Skrypa
"""

from typing import TYPE_CHECKING, Any, Callable, Optional, Type

from ds_tools.caching.mixins import ClearableCachedProperty

if TYPE_CHECKING:
    from .track import SongFile

__all__ = ['MusicFileProperty', 'TextTagProperty', 'TagValuesProperty']
_NotSet = object()


class MusicFileProperty(ClearableCachedProperty):
    _set_name = True

    def __init__(self, name):
        self.parts = name.split('.')

    def __get__(self, obj, owner):
        if obj is None:
            return self
        value = obj._f
        for part in self.parts:
            value = getattr(value, part)
        obj.__dict__[self.name] = value
        return value


class TextTagProperty(ClearableCachedProperty):
    _set_name = True

    def __init__(self, name: str, cast_func: Optional[Callable] = None, default: Any = _NotSet, save: bool = False):
        self.tag_name = name
        self.cast_func = cast_func
        self.default = default
        self.save = save

    def __get__(self, instance: 'SongFile', cls: Type['SongFile']):
        if instance is None:
            return self
        if value := instance.tag_text(self.tag_name, default=self.default):
            value = value.replace('\xa0', ' ')
        if self.cast_func is not None and value != self.default:
            value = self.cast_func(value)
        instance.__dict__[self.name] = value
        return value

    def __set__(self, instance, value):
        instance.set_text_tag(self.tag_name, value, by_id=False, save=self.save)

    def __delete__(self, instance):
        instance.delete_tag(instance.tag_name_to_id(self.tag_name), save=self.save)


class TagValuesProperty(TextTagProperty):
    def __get__(self, instance: 'SongFile', cls: Type['SongFile']):
        if instance is None:
            return self
        if values := instance.get_tag_values(self.tag_name, default=self.default):
            values = [value.replace('\xa0', ' ') for value in values if value is not None]
        if self.cast_func is not None:
            values = list(map(self.cast_func, values))
        instance.__dict__[self.name] = values
        return values
