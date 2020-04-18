"""
:author: Doug Skrypa
"""

import logging
import re
from copy import deepcopy
from typing import (
    Optional, Type, Union, Any, Callable, Set, Pattern, List, Iterable, Tuple, Collection, Mapping, TypeVar, Dict
)

from ds_tools.caching import ClearableCachedPropertyMixin
from ds_tools.compat import cached_property
from ds_tools.unicode.hangul import hangul_romanized_permutations_pattern
from ds_tools.unicode.languages import LangCat, J2R
from .extraction import split_enclosed
from .fuzz import fuzz_process, revised_weighted_ratio
from .spellcheck import is_english, english_probability

__all__ = ['Name', 'sort_name_parts']
log = logging.getLogger(__name__)
non_word_char_sub = re.compile(r'\W').sub
NamePartType = TypeVar('NamePartType')


class NamePart:
    """Facilitates resetting of cached properties on value changes"""
    def __init__(self, value_type: Optional[Type[NamePartType]] = None):
        self.type = value_type

    def __set_name__(self, owner: Type['Name'], name: str):
        owner._parts.add(name)
        self.name = name    # Note: when both __get__ and __set__ are defined, descriptor takes precedence over __dict__

    def __get__(self, instance: Optional['Name'], owner: Type['Name']) -> Optional[NamePartType]:
        if instance is None:
            return self
        return instance.__dict__.get(self.name)

    def __set__(self, instance: 'Name', value: Optional[NamePartType]):
        if self.type is not None and value is not None and not isinstance(value, self.type):
            raise TypeError(f'Unexpected type={type(value).__name__} for {instance!r}.{self.name} = {value!r}')
        instance.__dict__[self.name] = value
        if getattr(instance, '_Name__clear', False):            # works for both class property + instance property
            instance.clear_cached_properties()


class Name(ClearableCachedPropertyMixin):
    __clear = False                 # Prevent unnecessary cached property reset on init
    _parts = set()                  # Populated automatically by NamePart
    _english = NamePart(str)
    non_eng = NamePart(str)
    romanized = NamePart(str)
    lit_translation = NamePart(str)
    versions = NamePart(List)
    extra = NamePart(Mapping)

    def __init__(
            self, eng: Optional[str] = None, non_eng: Optional[str] = None, romanized: Optional[str] = None,
            lit_translation: Optional[str] = None, versions: Optional[Collection['Name']] = None,
            extra: Optional[Mapping[str, Any]] = None
    ):
        self._english = eng
        self.non_eng = non_eng
        self.romanized = romanized
        self.lit_translation = lit_translation
        self.versions = versions or []
        self.extra = extra
        self.__clear = True

    def __repr__(self):
        parts = (self.english, self.non_eng, self.extra)
        parts = ', '.join(map(repr, filter(None, parts)))
        return f'<{type(self).__name__}({parts})>'

    def _full_repr(self, include_no_val=False):
        var_names = ('_english', 'non_eng', 'romanized', 'lit_translation', 'extra', 'non_eng_lang', 'versions')
        vars = (getattr(self, attr) for attr in var_names)
        indent = ' ' * 4
        parts = ',\n'.join(f'{indent}{k}={v!r}' for k, v in zip(var_names, vars) if v or include_no_val)
        return f'<{type(self).__name__}(\n{parts}\n)>'

    def __str__(self):
        eng = self.english
        non_eng = self.non_eng
        if eng and non_eng:
            return f'{eng} ({non_eng})'
        return eng or non_eng

    def artist_str(self, group=True, members=True):
        if extra := self.extra:
            parts = [str(self)]
            if group and (_group := extra.get('group')):
                # noinspection PyUnboundLocalVariable
                parts.append(f'({_group})')
            if members and (_members := extra.get('members')):
                # noinspection PyUnboundLocalVariable
                parts.append('({})'.format(', '.join(m.artist_str() for m in _members)))
            return ' '.join(parts)
        else:
            return str(self)

    def __bool__(self):
        return bool(self._english or self.non_eng or self.romanized or self.lit_translation)

    def __lt__(self, other: 'Name'):
        return (self.english, self.non_eng) < (other.english, other.non_eng)

    @cached_property
    def __parts(self):
        return tuple(getattr(self, part) for part in self._parts if part not in ('versions', 'extra'))

    def __eq__(self, other: 'Name'):
        for part in self._parts:
            try:
                if getattr(self, part) != getattr(other, part):
                    return False
            except AttributeError:
                return False
        return True

    def __hash__(self):
        return hash(self.__parts)

    def _score(self, other: Union['Name', str], romanization_match=95, other_versions=True):
        if isinstance(other, str):
            other = Name(other)
        scores = []
        if self.non_eng_nospace and other.non_eng_nospace and self.non_eng_langs == other.non_eng_langs:
            scores.append(revised_weighted_ratio(self.non_eng_nospace, other.non_eng_nospace))
        if self.eng_fuzzed_nospace and other.eng_fuzzed_nospace:
            scores.append(revised_weighted_ratio(self.eng_fuzzed_nospace, other.eng_fuzzed_nospace))
        if self.non_eng_nospace and other.eng_fuzzed_nospace and self.has_romanization(other.eng_fuzzed_nospace, False):
            scores.append(romanization_match)
        if other.non_eng_nospace and self.eng_fuzzed_nospace and other.has_romanization(self.eng_fuzzed_nospace, False):
            scores.append(romanization_match)

        s_versions = self.versions
        if s_versions:
            for version in s_versions:
                scores.extend(version._score(other, romanization_match=romanization_match))
        if other_versions:
            o_versions = other.versions
            if o_versions:
                for version in o_versions:
                    scores.extend(self._score(version, romanization_match=romanization_match, other_versions=False))

        return scores

    def matches(self, other: Union['Name', str], threshold=80, agg_func: Callable = max, romanization_match=95):
        scores = self._score(other, romanization_match)
        if scores:
            return agg_func(scores) >= threshold
        return False

    def set_eng_or_rom(self, text: str, probability: Optional[float] = None, value: Optional[str] = None):
        """
        :param str text: The text that should be stored as either this Name's english or romanized version
        :param float probability: If specified, consider the given text to be English if :func:`english_probability
          <.spellcheck.english_probability>` returns a value greater than or equal to the specified value
        :param str value: The value to use after checking the Englishness of the provided text (defaults to the provided
          text)
        """
        if probability is not None:
            is_eng = english_probability(text) >= probability
        else:
            is_eng = is_english(text)
        if is_eng:
            self._english = value or text
        else:
            self.romanized = value or text

    def update(self, **kwargs):
        name_parts = self._parts
        for key, val in kwargs.items():
            if key in name_parts:
                setattr(self, key, val)
            else:
                raise ValueError(f'Invalid name part: {key!r}')

    def is_version_of(self, other: 'Name') -> bool:
        if (s_eng := self.english) and (o_eng := other.english) and (s_ne := self.non_eng) and (o_ne := other.non_eng):
            # noinspection PyUnboundLocalVariable
            return (s_eng == o_eng and s_ne != o_ne) or (s_ne == o_ne and s_eng != o_eng)
        return False

    def is_compatible_with(self, other: 'Name') -> bool:
        if self.is_version_of(other):
            return True
        s_eng, o_eng, s_ne, o_ne = self.english, other.english, self.non_eng, other.non_eng
        eng_match = s_eng and o_eng and s_eng == o_eng and xor(s_ne, o_ne)
        non_eng_match = xor(s_eng, o_eng) and s_ne and o_ne and s_ne == o_ne
        return eng_match or non_eng_match

    def _combined(self, other: 'Name') -> Dict[str, Any]:
        if self.is_version_of(other):
            combined = {attr: getattr(self, attr) for attr in self._parts}
            combined['versions'].append(other)
        else:
            combined = {}
            for attr in self._parts:
                s_value = getattr(self, attr)
                o_value = getattr(other, attr)
                if attr == 'versions':
                    combined[attr] = s_value + o_value
                elif attr == 'extra' and s_value and o_value:
                    combined[attr] = combo_value = deepcopy(s_value)
                    combo_value.update(o_value)
                else:
                    combined[attr] = s_value or o_value
        return combined

    def __add__(self, other: 'Name') -> 'Name':
        combined = self.__class__()
        combined.update(**self._combined(other))
        return combined

    def __iadd__(self, other: 'Name') -> 'Name':
        self.update(**self._combined(other))
        return self

    @cached_property
    def english(self) -> Optional[str]:
        eng = self._english or self.lit_translation
        if not eng and not self.non_eng and self.romanized:
            eng = self.romanized
        return eng

    @cached_property
    def eng_lower(self) -> Optional[str]:
        eng = self.english
        return eng.lower() if eng else None

    @cached_property
    def eng_fuzzed(self) -> Optional[str]:
        return fuzz_process(self.english)

    @cached_property
    def eng_fuzzed_nospace(self) -> Optional[str]:
        fuzzed = self.eng_fuzzed
        return ''.join(fuzzed.split()) if fuzzed else None

    @cached_property
    def non_eng_nospace(self) -> Optional[str]:
        non_eng = self.non_eng
        return ''.join(non_eng.split()) if non_eng else None

    @cached_property
    def non_eng_nospecial(self) -> Optional[str]:
        non_eng_nospace = self.non_eng_nospace
        return non_word_char_sub('', non_eng_nospace) if non_eng_nospace else None

    @cached_property
    def non_eng_lang(self) -> LangCat:
        return LangCat.categorize(self.non_eng)

    @cached_property
    def non_eng_langs(self) -> Set[LangCat]:
        return LangCat.categorize(self.non_eng, True)

    def has_romanization(self, text: str, fuzz=True) -> bool:
        """
        :param str text: A string that may be a romanized version of this Name's non-english component
        :param bool fuzz: Whether the given text needs to be fuzzed before attempting to compare it
        :return bool: True if the given text is a romanized version of this Name's non-english component
        """
        fuzzed = fuzz_process(text, space=False) if fuzz else text
        if not fuzzed:
            return False
        if self.korean:
            if self._romanization_pattern.match(fuzzed):
                return True
        other = self.japanese or self.cjk
        if other:
            return fuzzed in self._romanizations
        return False

    @cached_property
    def korean(self) -> Optional[str]:
        non_eng_lang = self.non_eng_lang
        expected = LangCat.HAN
        if non_eng_lang == expected or non_eng_lang == LangCat.MIX and expected in self.non_eng_langs:
            return self.non_eng
        return None

    @cached_property
    def japanese(self) -> Optional[str]:
        non_eng_lang = self.non_eng_lang
        expected = LangCat.JPN
        if non_eng_lang == expected or non_eng_lang == LangCat.MIX and expected in self.non_eng_langs:
            return self.non_eng
        return None

    @cached_property
    def cjk(self) -> Optional[str]:
        non_eng_lang = self.non_eng_lang
        expected = LangCat.CJK
        if non_eng_lang == expected or non_eng_lang == LangCat.MIX and expected in self.non_eng_langs:
            return self.non_eng
        return None

    @cached_property
    def _romanization_pattern(self) -> Pattern:
        return hangul_romanized_permutations_pattern(self.non_eng_nospecial, False)

    @cached_property
    def _romanizations(self) -> List[str]:
        text = self.non_eng_nospace if self.japanese or self.cjk else None
        if text:
            return [j2r.romanize(text) for j2r in J2R.romanizers(False)]
        return []

    @classmethod
    def from_enclosed(cls, name: str) -> 'Name':
        if LangCat.categorize(name) == LangCat.MIX:
            parts = split_enclosed(name, reverse=True, maxsplit=1)
        else:
            parts = (name,)
        return cls.from_parts(parts)

    @classmethod
    def from_parts(cls, parts: Iterable[str]) -> 'Name':
        eng = None
        non_eng = None
        extra = []
        name = None
        for part in parts:
            if name is not None:
                extra.append(part)
            elif not non_eng and LangCat.contains_any(part, LangCat.non_eng_cats):
                non_eng = part
            elif not eng and LangCat.contains_any(part, LangCat.ENG):
                eng = part
            elif eng and non_eng and LangCat.categorize(part) == LangCat.ENG:
                name = cls(eng, non_eng)
                if name.has_romanization(part):
                    name.romanized = part
                elif name.has_romanization(eng) and not is_english(eng) and is_english(part):
                    name._english = part
                    name.romanized = eng
                else:
                    name = None
                    extra.append(part)
            else:
                extra.append(part)

        if name is None and eng or non_eng:
            name = cls(eng, non_eng)
        if name is None:
            raise ValueError(f'Unable to find any valid name parts from {parts!r}')
        if extra:
            name.extra = {'unknown': extra}
        return name


class _NamePart:
    __slots__ = ('pos', 'value', 'cat')

    def __init__(self, pos: int, value: str):
        self.pos = pos
        self.value = value
        self.cat = LangCat.categorize(value)

    def __lt__(self, other: '_NamePart'):
        s_cat = self.cat
        o_cat = other.cat
        if s_cat == o_cat:
            return self.pos < other.pos

        mix = LangCat.MIX
        eng = LangCat.ENG
        if o_cat == mix and s_cat == eng:
            return True
        elif s_cat == mix and o_cat == eng:
            return False
        return s_cat < o_cat


def sort_name_parts(parts: Iterable[str]) -> Tuple[str, ...]:
    return tuple(p.value for p in sorted(_NamePart(i, part) for i, part in enumerate(parts)))


def xor(a, b):
    return bool(a) ^ bool(b)
