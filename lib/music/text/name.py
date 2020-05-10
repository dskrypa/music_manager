"""
:author: Doug Skrypa
"""

import logging
import re
from copy import copy, deepcopy
from typing import (
    Optional, Type, Union, Any, Callable, Set, Pattern, List, Iterable, Collection, Mapping, TypeVar, Dict
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
    versions = NamePart(Set)
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
        self.versions = set(versions) if versions else set()
        self.extra = extra
        self.__clear = True

    def __repr__(self):
        return self.full_repr(pretty=True)

    def __copy__(self):
        attrs = self.as_dict()
        attrs['eng'] = attrs.pop('_english')
        return self.__class__(**attrs)

    def as_dict(self):
        return {attr: deepcopy(getattr(self, attr)) for attr in self._parts}

    def full_repr(self, include_no_val=False, delim='', indent=1, inner=False, include_versions=True, pretty=False):
        var_names = [
            'non_eng', 'romanized', 'lit_translation', 'extra', # 'non_eng_lang'
        ]
        var_vals = [getattr(self, attr) for attr in var_names]
        indent_str = ' ' * indent
        if pretty and delim == '' and self.english and self.english == self._english:
            _parts = [repr(self.english)]
        else:
            _parts = [f'_english={self._english!r}']

        _parts.extend(f'{k}={v!r}' for k, v in zip(var_names, var_vals) if v or include_no_val)
        parts = f',{delim}{indent_str}'.join(_parts)
        if (versions := self.versions) and include_versions:
            if parts:
                parts += f',{delim}{indent_str}'
            if '\n' in delim:
                inner_indent = ' ' * (indent + 4)
                fmt = f'versions={{{{{delim}{inner_indent}{{}}{delim}{indent_str}}}}}'
            else:
                inner_indent = indent_str
                fmt = 'versions={{{}}}'
            parts += fmt.format(
                f',{delim}{inner_indent}'.join(v.full_repr(include_no_val, inner=True) for v in versions)
            )

        prefix = f'{delim}{indent_str}' if '\n' in delim else delim
        suffix = f'{delim}{indent_str}' if inner and '\n' in delim else delim
        return f'<{type(self).__name__}({prefix}{parts}{suffix})>'

    def __str__(self):
        eng = self.english
        non_eng = self.non_eng
        if eng and non_eng:
            return f'{eng} ({non_eng})'
        return eng or non_eng or self.romanized or self.lit_translation or ''

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
        return (self.english or '', self.non_eng or '') < (other.english or '', other.non_eng or '')

    @cached_property
    def __parts(self):
        # _english, non_eng, romanized, lit_translation
        return tuple(getattr(self, part) for part in self._parts if part not in ('versions', 'extra'))

    def __eq__(self, other: 'Name'):
        for part in self._parts:
            try:
                if getattr(self, part) != getattr(other, part):
                    # log.debug(f'{self!r}.{part}={getattr(self, part)!r} != {other!r}.{part}={getattr(other, part)!r}')
                    return False
            except AttributeError:
                return False
        return True

    def __hash__(self):
        return hash(self.__parts)

    def _score(self, other: Union['Name', str], romanization_match=95, other_versions=True):
        if isinstance(other, str):
            other = Name.from_parts(split_enclosed(other, reverse=True, maxsplit=1))
        # log.debug(f'Scoring match:\n{self.full_repr()}._score(\n{other.full_repr()})')
        scores = []
        if self.non_eng_nospace and other.non_eng_nospace and self.non_eng_langs == other.non_eng_langs:
            scores.append(revised_weighted_ratio(self.non_eng_nospace, other.non_eng_nospace))
        if self.eng_fuzzed_nospace and other.eng_fuzzed_nospace:
            scores.append(revised_weighted_ratio(self.eng_fuzzed_nospace, other.eng_fuzzed_nospace))
        if self.non_eng_nospace and other.eng_fuzzed_nospace and self.has_romanization(other.eng_fuzzed_nospace, False):
            scores.append(romanization_match)
        if other.non_eng_nospace and self.eng_fuzzed_nospace and other.has_romanization(self.eng_fuzzed_nospace, False):
            scores.append(romanization_match)

        if s_versions := self.versions:
            for version in s_versions:
                scores.extend(version._score(other, romanization_match=romanization_match))
        if other_versions:
            if o_versions := other.versions:
                for version in o_versions:
                    scores.extend(self._score(version, romanization_match=romanization_match, other_versions=False))

        # log.debug(f'{self!r}.matches({other!r}) {scores=}')
        return scores

    def matches(self, other: Union['Name', str], threshold=90, agg_func: Callable = max, romanization_match=95):
        scores = self._score(other, romanization_match)
        if scores:
            score = agg_func(scores)
            # log.debug(f'{self!r}.matches({other!r}) {score=}')
            return score >= threshold
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
                if key == 'versions' and not isinstance(val, set):
                    val = set(val)
                setattr(self, key, val)
            else:
                raise ValueError(f'Invalid name part: {key!r}')

    def with_part(self, **kwargs):
        _copy = copy(self)
        _copy.update(**kwargs)
        return _copy

    def _match(self, other: 'Name', attr: str):
        return _match(getattr(self, attr), getattr(other, attr))

    def _matches(self, other: 'Name'):
        return tuple(self._match(other, attr) for attr in ('english', 'non_eng'))

    def _basic_matches(self, other: 'Name'):
        return tuple(self._match(other, attr) for attr in ('_english', 'non_eng', 'romanized', 'lit_translation'))

    def _merge_basic(self, other: 'Name'):
        merged = {}
        for attr in ('_english', 'non_eng', 'romanized', 'lit_translation'):
            s_value = getattr(self, attr)
            o_value = getattr(other, attr)
            if s_value and o_value and s_value != o_value:
                raise ValueError(f'Unable to merge {self!r} and {other!r} because {attr=!r} does not match')
            merged[attr] = s_value or o_value
        return merged

    def _merge_complex(self, other: 'Name'):
        extra = deepcopy(self.extra) or {}
        if o_extra := other.extra:
            extra.update(o_extra)
        return {'extra': extra or None, 'versions': self._merge_versions(other)}

    def _merge_versions(self, other: 'Name', include=False):
        versions = set()
        for version in self.versions:
            try:
                version._merge_basic(other)
            except ValueError:
                versions.add(version)
        for version in other.versions:
            try:
                version._merge_basic(self)
            except ValueError:
                versions.add(version)

        if include:
            other = copy(other)
            other._pop_versions()
            versions.add(other)
        return versions

    def is_version_of(self, other: 'Name', partial=False) -> bool:
        matches = self._matches(other)
        any_match = any(matches)
        if partial:
            return any_match
        elif any_match:
            return not any(m is False for m in matches)
        return False

    def should_merge(self, other: 'Name'):
        matches = self._matches(other)
        return any(matches) and not any(m is False for m in matches) and self != other

    def _pop_versions(self):
        versions = self.versions
        self.versions = set()
        return versions

    def _combined(self, other: 'Name') -> Dict[str, Any]:
        try:
            combined = self._merge_basic(other)
        except ValueError:
            combined = self.as_dict()
            combined['versions'] = self._merge_versions(other, True)
        else:
            combined.update(self._merge_complex(other))
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
    def eng_lang(self) -> LangCat:
        return LangCat.categorize(self.english)

    @cached_property
    def eng_langs(self) -> Set[LangCat]:
        return LangCat.categorize(self.english, True)

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
    def from_enclosed(cls, name: str, **kwargs) -> 'Name':
        if LangCat.categorize(name) == LangCat.MIX:
            parts = split_enclosed(name, reverse=True, maxsplit=1)
        else:
            parts = (name,)
        return cls.from_parts(parts, **kwargs)

    @classmethod
    def split(cls, name: str, **kwargs) -> 'Name':
        return cls.from_parts(LangCat.split(name), **kwargs)

    @classmethod
    def from_parts(cls, parts: Iterable[str], **kwargs) -> 'Name':
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
                name = cls(eng, non_eng, **kwargs)
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

        if name is None:
            if eng or non_eng:
                name = cls(eng, non_eng, **kwargs)
            elif extra and len(extra) == 1:
                name = cls(extra[0], **kwargs)
                extra = None
        if name is None:
            raise ValueError(f'Unable to find any valid name parts from {parts!r}; found {extra=!r}')
        if extra:
            if name.extra:
                # noinspection PyTypeChecker
                name.extra['unknown'] = extra
            else:
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


def sort_name_parts(parts: Iterable[str]) -> List[Optional[str]]:
    parts = list(p.value for p in sorted(_NamePart(i, part) for i, part in enumerate(parts)))
    if parts and not LangCat.contains_any(parts[0], LangCat.ENG):
        parts.insert(0, None)
    return parts


def _match(a, b):
    if a and b:
        return a == b
    return None


def xor(a, b):
    return bool(a) ^ bool(b)
