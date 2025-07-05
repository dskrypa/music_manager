"""
:author: Doug Skrypa
"""

from __future__ import annotations

import logging
import re
from copy import copy, deepcopy
from functools import reduce
from operator import xor
from typing import TYPE_CHECKING, Type, Any, Collection, Iterable, Iterator, TypeVar, MutableMapping, Mapping, Union

from ds_tools.caching.decorators import ClearableCachedPropertyMixin, cached_property
from ds_tools.unicode.hangul import hangul_romanized_permutations_pattern
from ds_tools.unicode.languages import LangCat, J2R

from .extraction import split_enclosed
from .fuzz import fuzz_process, revised_weighted_ratio
from .spellcheck import is_english, english_probability
from .utils import combine_with_parens

if TYPE_CHECKING:
    from typing import Pattern
    from music.typing import OptStr, StrIter

__all__ = ['Name', 'sort_name_parts']
log = logging.getLogger(__name__)

non_word_char_sub = re.compile(r'\W').sub
NamePartType = TypeVar('NamePartType')
NameLike = Union['Name', str]


class NamePart:
    """Facilitates resetting of cached properties on value changes"""
    __slots__ = ('type', 'name')

    def __init__(self, value_type: Type[NamePartType] = None):
        self.type = value_type

    def __set_name__(self, owner: Type[Name], name: str):
        owner._parts.add(name)
        self.name = name    # Note: when both __get__ and __set__ are defined, descriptor takes precedence over __dict__

    def __get__(self, instance: Name | None, owner: Type[Name]) -> NamePartType | None:
        if instance is None:
            return self
        return instance.__dict__.get(self.name)

    def __set__(self, instance: Name, value: NamePartType | None):
        if self.type is not None and value is not None and not isinstance(value, self.type):
            raise TypeError(f'Unexpected type={type(value).__name__} for {instance!r}.{self.name} = {value!r}')
        instance.__dict__[self.name] = value
        if getattr(instance, '_Name__clear', False):            # works for both class property + instance property
            instance.clear_cached_properties()


class Name(ClearableCachedPropertyMixin):
    __clear = False                     # Prevent unnecessary cached property reset on init
    _parts = set()                      # Populated automatically by NamePart
    _english = NamePart(str)            # type: OptStr
    non_eng = NamePart(str)             # type: OptStr
    romanized = NamePart(str)           # type: OptStr
    lit_translation = NamePart(str)     # type: OptStr
    versions = NamePart(set)            # type: set[Name]
    extra = NamePart(MutableMapping)    # type: MutableMapping[str, Any] | None

    # region Constructors

    def __init__(
        self,
        eng: str = None,
        non_eng: str = None,
        romanized: str = None,
        lit_translation: str = None,
        versions: Iterable[Name] = None,
        extra: MutableMapping[str, Any] = None,
    ):
        self._english = eng
        self.non_eng = non_eng
        self.romanized = romanized
        self.lit_translation = lit_translation
        self.versions = set(versions) if versions else set()
        self.extra = extra
        self.__clear = True

    @classmethod
    def from_enclosed(cls, name: str, **kwargs) -> Name:
        if LangCat.categorize(name) == LangCat.MIX:
            parts = split_enclosed(name, reverse=True, maxsplit=1)
        else:
            parts = (name,)
        return cls.from_parts(parts, **kwargs)

    @classmethod
    def from_parts(cls, parts: StrIter, **kwargs) -> Name:
        eng = None
        non_eng = None
        unknown = []
        name = None
        for part in parts:
            if not part:
                continue
            elif name is not None:
                unknown.append(part)
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
                    unknown.append(part)
            else:
                unknown.append(part)

        if name is None:
            if eng or non_eng:
                name = cls(eng, non_eng, **kwargs)
            elif unknown and len(unknown) == 1:
                return cls(unknown[0], **kwargs)

        if name is None:
            raise ValueError(f'Unable to find any valid name parts from {parts!r}; found {unknown=}')
        if unknown:
            name.add_extra('unknown', unknown)
        return name

    # endregion

    def as_dict(self) -> dict[str, None | str | MutableMapping[str, Any] | set[Name]]:
        return {attr: deepcopy(getattr(self, attr)) for attr in self._parts}

    def full_repr(
        self,
        include_no_val: bool = False,
        delim: str = '',
        indent: int = 1,
        inner: bool = False,
        include_versions: bool = True,
        pretty: bool = False,
        attrs: StrIter = None,
    ) -> str:
        var_names = [
            'non_eng', 'romanized', 'lit_translation', 'extra',  # 'non_eng_lang'
        ]
        if attrs:
            var_names.extend(attrs)
        var_vals = [getattr(self, attr, None) for attr in var_names]
        indent_str = ' ' * indent
        if pretty and delim == '' and self.english and self.english == self._english:
            _parts = [repr(self.english)]
        else:
            _parts = [f'_english={self._english!r}']

        _parts.extend(f'{k}={v!r}' for k, v in zip(var_names, var_vals) if v or include_no_val)
        if self._is_ost:
            _parts.append('_is_ost=True')
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

    def artist_str(self, group: bool = True, members: bool = True) -> str:
        if extra := self.extra:
            parts = [str(self)]
            if group and (_group := extra.get('group')):
                parts.append(f'({_group})')
            if members and (_members := extra.get('members')):
                parts.append('({})'.format(', '.join(m.artist_str() for m in _members)))
            return ' '.join(parts)
        else:
            return str(self)

    def split(self) -> Name:
        return self.from_parts(LangCat.split(self.english), versions={self, Name(non_eng=self.english)})

    # region Internal / Dunder Methods

    def __str__(self) -> str:
        eng = self.english
        non_eng = self.non_eng
        if eng and non_eng:
            return combine_with_parens([eng, non_eng])
        return eng or non_eng or self.romanized or self.lit_translation or ''

    def __repr__(self) -> str:
        return self.full_repr(pretty=True)

    def __rich_repr__(self):
        for attr in ('_english', 'non_eng', 'romanized', 'lit_translation', 'extra', '_is_ost', 'versions'):
            if value := getattr(self, attr):
                yield attr, value

    def __copy__(self):
        attrs = self.as_dict()
        attrs['eng'] = attrs.pop('_english')
        return self.__class__(**attrs)

    def __bool__(self) -> bool:
        return bool(self._english or self.non_eng or self.romanized or self.lit_translation)

    @cached_property
    def __parts(self):
        # _english, non_eng, romanized, lit_translation
        return tuple(getattr(self, part) for part in self._parts if part not in ('versions', 'extra'))

    def __lt__(self, other: Name) -> bool:
        return (self.english or '', self.non_eng or '') < (other.english or '', other.non_eng or '')

    def __eq__(self, other: Name) -> bool:
        for part in self._parts:
            try:
                if getattr(self, part) != getattr(other, part):
                    # log.debug(f'{self!r}.{part}={getattr(self, part)!r} != {other!r}.{part}={getattr(other, part)!r}')
                    return False
            except AttributeError:
                return False
        return True

    def __hash__(self) -> int:
        return reduce(xor, map(hash, self.__parts))  # noqa

    def __add__(self, other: Name) -> Name:
        combined = self.__class__()
        combined.update(**self._combined(other))
        return combined

    def __iadd__(self, other: Name) -> Name:
        self.update(**self._combined(other))
        return self

    def __iter__(self) -> Iterator[str]:
        for part in (self._english, self.non_eng, self.romanized, self.lit_translation):
            if part:
                yield part

    # endregion

    # region Name Matching

    def is_version_of(self, other: Name, partial: bool = False) -> bool:
        matches = self._matches(other)
        any_match = any(matches)
        if partial:
            return any_match
        elif any_match:
            return not any(m is False for m in matches)
        return False

    def matches(self, other: NameLike, threshold: int = 90, rom_match_score: int = 95) -> bool:
        return any(score >= threshold for score in self._score(_normalize_name(other), rom_match_score))

    def matches_any(self, others: Iterable[NameLike], *args, **kwargs) -> bool:
        return any(self.matches(other, *args, **kwargs) for other in others)

    def should_merge(self, other: Name) -> bool:
        matches = self._matches(other)
        return any(matches) and not any(m is False for m in matches) and self != other

    def has_romanization(self, text: str, fuzz: bool = True) -> bool:
        """
        :param text: A string that may be a romanized version of this Name's non-english component
        :param fuzz: Whether the given text needs to be fuzzed before attempting to compare it
        :return: True if the given text is a romanized version of this Name's non-english component
        """
        fuzzed = fuzz_process(text, space=False) if fuzz else text
        if not fuzzed:
            return False
        if self.korean and self._romanization_pattern.match(fuzzed):
            return True
        if self.japanese or self.cjk:  # Not mutually exclusive with previous condition
            return fuzzed in self._romanizations
        return False

    def find_best_match(self, others: Collection[NameLike], threshold: int = 90, **kwargs) -> Name | None:
        try:
            return max(self.find_best_matches(others, threshold, **kwargs))[1]
        except ValueError as e:
            if 'max() iterable argument is empty' in e.args:
                return None
            raise

    def find_best_matches(
        self,
        others: Collection[NameLike],
        threshold: int = 90,
        *,
        rom_match_score: int = 95,
        other_versions: bool = True,
        try_alt: bool = True,
        try_ost: bool = True,
    ) -> Iterator[tuple[int, Name]]:
        for other in map(_normalize_name, others):
            score = self.get_match_score(
                other, rom_match_score=rom_match_score, other_versions=other_versions, try_alt=try_alt, try_ost=try_ost
            )
            if score >= threshold:
                yield score, other

    def get_match_score(
        self,
        other: NameLike,
        *,
        rom_match_score: int = 95,
        other_versions: bool = True,
        try_alt: bool = True,
        try_ost: bool = True,
    ) -> int:
        try:
            return max(self._score(_normalize_name(other), rom_match_score, other_versions, try_alt, try_ost))
        except ValueError as e:
            if 'max() iterable argument is empty' in e.args:
                return 0
            raise

    def get_match_scores(
        self,
        other: NameLike,
        *,
        rom_match_score: int = 95,
        other_versions: bool = True,
        try_alt: bool = True,
        try_ost: bool = True,
    ) -> list[int]:
        # log.debug(f'{self!r}.matches({other!r}) {scores=}', extra={'color': (11, 12)})
        return list(self._score(_normalize_name(other), rom_match_score, other_versions, try_alt, try_ost))

    def _score(
        self,
        other: Name,
        rom_match_score: int = 95,
        other_versions: bool = True,
        try_alt: bool = True,
        try_ost: bool = True,
    ) -> Iterator[int]:
        # log.debug(
        #     f'Scoring match:\n{self.full_repr(attrs=["eng_langs", "non_eng_langs"])}'
        #     f'._score(\n{other.full_repr(attrs=["eng_langs", "non_eng_langs"])})',
        #     extra={'color': 11}
        # )
        ep_score = None
        if self.non_eng_nospace and other.non_eng_nospace and self.non_eng_langs == other.non_eng_langs:
            score = revised_weighted_ratio(self.non_eng_nospace, other.non_eng_nospace)
            if score == 100 and self._english and other._english:
                ep_score = self._score_eng_parts(other)
                score = (score + ep_score) // 2
            # log.debug(f'score({self.non_eng_nospace=}, {other.non_eng_nospace=}) => {score}', extra={'color': (0, 8)})
            yield score

        if self.eng_fuzzed_nospace and other.eng_fuzzed_nospace:
            yield revised_weighted_ratio(self.eng_fuzzed_nospace, other.eng_fuzzed_nospace)

        for a, b in ((self, other), (other, self)):
            if a.non_eng_nospace and b.eng_fuzzed_nospace and a.has_romanization(b.eng_fuzzed_nospace, False):
                if ep_score is not None:
                    yield (rom_match_score + ep_score) // 2
                else:
                    yield rom_match_score

        if try_alt:
            if self._is_asian_misclassified_as_eng():
                if self.split()._is_alt_romanization_match(other):
                    yield rom_match_score
            elif other._is_asian_misclassified_as_eng() and other.split()._is_alt_romanization_match(self):
                yield rom_match_score

        if self.versions:
            for version in self.versions:
                yield from version._score(other, rom_match_score, try_alt=try_alt, try_ost=try_ost)

        if other_versions and other.versions:
            for version in other.versions:
                yield from self._score(version, rom_match_score, other_versions=False, try_alt=try_alt, try_ost=try_ost)

        if try_ost:
            if self._is_ost:
                # log.debug(f'{self!r}: Trying {self.no_suffix_version!r}._score with {other!r}', extra={'color': (0, 8)})
                yield from self.no_suffix_version._score(other, rom_match_score, other_versions, try_alt, False)
            elif other._is_ost:
                # log.debug(f'{self!r}: Trying self._score with {other.no_suffix_version!r}', extra={'color': (0, 8)})
                yield from self._score(other.no_suffix_version, rom_match_score, other_versions, try_alt, False)

    def _is_asian_misclassified_as_eng(self) -> bool:
        return not self.non_eng and self.eng_lang == LangCat.MIX and self.eng_langs.intersection(LangCat.asian_cats)

    def _is_alt_romanization_match(self, other: Name) -> bool:
        if other.eng_fuzzed_nospace and self.eng_fuzzed_nospace:
            # log.debug(f'Trying alt_{self=} / {other.eng_fuzzed_nospace[len(self.eng_fuzzed_nospace):]!r}', extra={'color': (0, 8)})
            return (
                other.eng_fuzzed_nospace.startswith(self.eng_fuzzed_nospace)
                and self.has_romanization(other.eng_fuzzed_nospace[len(self.eng_fuzzed_nospace):])
            )
        return False

    def _score_eng_parts(self, other: Name) -> int:
        o_eng_parts = other.eng_parts
        if scores := [revised_weighted_ratio(s_part, o_part) for s_part in self.eng_parts for o_part in o_eng_parts]:
            return max(scores)
        return 100

    def _match(self, other: Name, attr: str) -> bool | None:
        return _match(getattr(self, attr), getattr(other, attr))

    def _matches(self, other: Name) -> tuple[bool | None, ...]:
        return tuple(self._match(other, attr) for attr in ('english', 'non_eng'))

    def _basic_matches(self, other: Name) -> tuple[bool | None, ...]:
        return tuple(self._match(other, attr) for attr in ('_english', 'non_eng', 'romanized', 'lit_translation'))

    # endregion

    # region Update / Combine Methods

    def set_eng_or_rom(self, text: str, probability: float = None, value: str = None):
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

    def update_extra(self, extra: Mapping[str, Any] = None, **kwargs):
        if self.extra is None and (extra or kwargs):
            self.extra = {}
        for data in (extra, kwargs):
            if data:
                self.extra.update(data)

    def add_extra(self, key: str, value: Any):
        if self.extra is None:
            self.extra = {key: value}
        else:
            self.extra[key] = value

    def with_extras(self, **kwargs) -> Name:
        clone = copy(self)
        for key, val in kwargs.items():
            clone.add_extra(key, val)
        return clone

    def with_part(self, **kwargs) -> Name:
        clone = copy(self)
        clone.update(**kwargs)
        return clone

    def _merge_basic(self, other: Name) -> dict[str, OptStr]:
        merged = {}
        for attr in ('_english', 'non_eng', 'romanized', 'lit_translation'):
            s_value = getattr(self, attr)
            o_value = getattr(other, attr)
            if s_value and o_value and s_value != o_value:
                raise ValueError(f'Unable to merge {self!r} and {other!r} because {attr=} does not match')
            merged[attr] = s_value or o_value
        return merged

    def _merge_complex(self, other: Name):
        extra = deepcopy(self.extra) or {}
        if o_extra := other.extra:
            extra.update(o_extra)
        return {'extra': extra or None, 'versions': self._merge_versions(other)}

    def _merge_versions(self, other: Name, include: bool = False) -> set[Name]:
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

    def _pop_versions(self):
        versions = self.versions
        self.versions = set()
        return versions

    def _combined(self, other: Name) -> dict[str, Any]:
        try:
            combined = self._merge_basic(other)
        except ValueError:
            combined = self.as_dict()
            combined['versions'] = self._merge_versions(other, True)
        else:
            combined.update(self._merge_complex(other))
        return combined

    # endregion

    # region Normalized Versions of Attributes

    @cached_property
    def no_suffix_version(self) -> Name | None:
        if self._is_ost:
            stripped = {key: p[:-4].strip() for key, p in self.as_dict().items() if p and p.upper().endswith(' OST')}
            # log.debug(f'{self!r}: {stripped=}')
            return self.with_part(**stripped)
        return None

    @cached_property
    def english(self) -> OptStr:
        eng = self._english or self.lit_translation
        if not eng and not self.non_eng and self.romanized:
            eng = self.romanized
        return eng

    @cached_property
    def eng_lower(self) -> OptStr:
        return self.english.lower() if self.english else None

    @cached_property
    def eng_fuzzed(self) -> OptStr:
        return fuzz_process(self.english)

    @cached_property
    def eng_fuzzed_nospace(self) -> OptStr:
        return ''.join(self.eng_fuzzed.split()) if self.eng_fuzzed else None

    @cached_property
    def eng_parts(self) -> set[str]:
        return set(filter(None, (self._english, self.lit_translation, self.romanized)))

    @cached_property
    def non_eng_lower(self) -> OptStr:
        non_eng = self.non_eng
        return non_eng.lower() if non_eng else None

    @cached_property
    def non_eng_nospace(self) -> OptStr:
        non_eng = self.non_eng
        return ''.join(non_eng.split()) if non_eng else None

    @cached_property
    def non_eng_nospecial(self) -> OptStr:
        non_eng_nospace = self.non_eng_nospace
        return non_word_char_sub('', non_eng_nospace) if non_eng_nospace else None

    @cached_property
    def _is_ost(self) -> bool:
        eng = self.eng_lower
        non_eng = self.non_eng_lower
        if eng or non_eng:
            return any(val.endswith(' ost') for val in filter(None, (eng, non_eng)))
        return False

    # endregion

    # region Language Categories

    @cached_property
    def eng_lang(self) -> LangCat:
        return LangCat.categorize(self.english)

    @cached_property
    def eng_langs(self) -> set[LangCat]:
        return LangCat.categorize(self.english, True)

    @cached_property
    def non_eng_lang(self) -> LangCat:
        return LangCat.categorize(self.non_eng)

    @cached_property
    def non_eng_langs(self) -> set[LangCat]:
        return LangCat.categorize(self.non_eng, True)

    # endregion

    # region Conditional Non-English Attributes

    @cached_property
    def korean(self) -> OptStr:
        return self._non_eng_if_expected(LangCat.HAN)

    @cached_property
    def japanese(self) -> OptStr:
        return self._non_eng_if_expected(LangCat.JPN)

    @cached_property
    def cjk(self) -> OptStr:
        return self._non_eng_if_expected(LangCat.CJK)

    @cached_property
    def _romanization_pattern(self) -> Pattern:
        return hangul_romanized_permutations_pattern(self.non_eng_nospecial, False)

    @cached_property
    def _romanizations(self) -> list[str]:
        if text := self.non_eng_nospace if self.japanese or self.cjk else None:
            return list(J2R().romanize(text))
        return []

    def _non_eng_if_expected(self, expected: LangCat) -> OptStr:
        non_eng_lang = self.non_eng_lang
        if non_eng_lang == expected or non_eng_lang == LangCat.MIX and expected in self.non_eng_langs:
            return self.non_eng
        return None

    # endregion


class _NamePart:
    __slots__ = ('pos', 'value', 'cat')

    def __init__(self, pos: int, value: str):
        self.pos = pos
        self.value = value
        self.cat = LangCat.categorize(value)

    def __lt__(self, other: _NamePart) -> bool:
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


def sort_name_parts(parts: StrIter) -> list[OptStr]:
    parts = list(p.value for p in sorted(_NamePart(i, part) for i, part in enumerate(parts)))
    if parts and not LangCat.contains_any(parts[0], LangCat.ENG):
        parts.insert(0, None)
    return parts


def _match(a, b) -> bool | None:
    if a and b:
        return a == b
    return None


def _normalize_name(name: NameLike) -> Name:
    if isinstance(name, str):
        return Name.from_parts(split_enclosed(name, reverse=True, maxsplit=1))
    return name
