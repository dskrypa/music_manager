"""
:author: Doug Skrypa
"""

from __future__ import annotations

import re
from typing import Sequence, Iterable, Match

from ds_tools.core.decorate import cached_classproperty
from ds_tools.utils.text_processing import common_suffix

from .extraction import ends_with_enclosed, split_enclosed

__all__ = ['combine_with_parens', 'find_ordinal', 'title_case', 'NumberParser', 'parse_int_words']


def combine_with_parens(parts: Iterable[str]) -> str:
    if isinstance(parts, str):
        return parts
    if not isinstance(parts, Sequence):
        parts = sorted(parts)
    if len(parts) == 1:
        return parts[0]

    if (_suffix := common_suffix(parts)) and ends_with_enclosed(_suffix):
        suffix = f'({split_enclosed(_suffix, reverse=True, maxsplit=1)[-1]})'
        slen = len(suffix)
        parts = [part[:-slen].strip() for part in parts]
    else:
        suffix = None

    combined = '{} {}'.format(parts[0], ' '.join(f'({part})' for part in parts[1:]))
    return f'{combined} {suffix}' if suffix else combined


class OrdinalParser:
    @cached_classproperty
    def _ordinal_to_int(cls) -> dict[str, int]:  # noqa
        from ds_tools.output.formatting import ordinal_suffix

        ordinal_to_int = {
            'debut': 1,
            'first': 1, 'second': 2, 'third': 3, 'fourth': 4, 'fifth': 5,
            'sixth': 6, 'seventh': 7, 'eighth': 8, 'ninth': 9, 'tenth': 10,
            'eleventh': 11, 'twelfth': 12, 'thirteenth': 13, 'fourteenth': 14, 'fifteenth': 15,
            'sixteenth': 16, 'seventeenth': 17, 'eighteenth': 18, 'nineteenth': 19, 'twentieth': 20,
        }
        ordinal_to_int.update((f'{i}{ordinal_suffix(i)}', i) for i in range(1, 21))
        return ordinal_to_int

    @cached_classproperty
    def _ord_search(cls):  # noqa
        import re

        return re.compile(f'({"|".join(cls._ordinal_to_int)})', re.IGNORECASE).search

    def parse(self, text: str) -> int | None:
        if m := self._ord_search(text.lower()):
            return self._ordinal_to_int[m.group(1)]
        return None


find_ordinal = OrdinalParser().parse


CAPITALIZE_SUB = re.compile(r'\b\w+\b', re.IGNORECASE).sub


def title_case(text: str):
    num = 0

    def _capitalize(match: Match) -> str:
        group = match.group(0)
        nonlocal num
        num += 1
        if num == 1:
            return group[0].upper() + group[1:].lower()
        lc_group = group.lower()
        if lc_group in {'an', 'to', 'in', 'a', 'by', 'the', 'and', 'but', 'for', 'at', 'of'}:
            return lc_group
        return group[0].upper() + group[1:].lower()

    return CAPITALIZE_SUB(_capitalize, text)


class NumberParser:
    @cached_classproperty
    def magnitudes(cls) -> dict[str, int]:  # noqa
        names = ['hundred', 'thousand', 'million', 'billion', 'trillion']
        return {word: 10 ** (i * 3 or 2) for i, word in enumerate(names)}

    @cached_classproperty
    def word_value_map(cls) -> dict[str, int]:  # noqa
        singles = [
            'zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight',
            'nine', 'ten', 'eleven', 'twelve', 'thirteen', 'fourteen', 'fifteen',
            'sixteen', 'seventeen', 'eighteen', 'nineteen',
        ]
        tens = ['', '', 'twenty', 'thirty', 'forty', 'fifty', 'sixty', 'seventy', 'eighty', 'ninety']
        return {w: i for i, w in enumerate(singles)} | {w: i * 10 for i, w in enumerate(tens) if w}

    def parse(self, text: str) -> int:
        try:
            return int(text.strip())
        except ValueError:
            pass

        current = result = 0
        for word in (w.lower() for w in map(str.strip, re.split(r'-|\s', text)) if w):
            if scale := self.magnitudes.get(word):
                result += current * scale
                current = 0
            elif (value := self.word_value_map.get(word)) is not None:
                current += value
            elif word != 'and':
                raise ValueError(f'Invalid number {word=}')

        return result + current


parse_int_words = NumberParser().parse
