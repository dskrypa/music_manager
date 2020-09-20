"""
:author: Doug Skrypa
"""

from typing import Sequence, Iterable, Optional

__all__ = ['combine_with_parens', 'find_ordinal']


def combine_with_parens(parts: Iterable[str]) -> str:
    if not isinstance(parts, Sequence):
        parts = list(parts)
    if len(parts) == 1:
        return parts[0]
    return '{} {}'.format(parts[0], ' '.join(f'({part})' for part in parts[1:]))


def find_ordinal(text: str) -> Optional[int]:
    try:
        ord_search = find_ordinal._ord_search
        ordinal_to_int = find_ordinal._ordinal_to_int
    except AttributeError:
        import re
        from ds_tools.utils.misc import num_suffix
        ordinal_to_int = find_ordinal._ordinal_to_int = {
            'first': 1, 'second': 2, 'third': 3, 'fourth': 4, 'fifth': 5, 'sixth': 6, 'seventh': 7, 'eighth': 8,
            'ninth': 9, 'tenth': 10, 'debut': 1
        }
        ordinal_to_int.update((f'{i}{num_suffix(i)}', i) for i in range(1, 21))
        ord_search = find_ordinal._ord_search = re.compile(f'({"|".join(ordinal_to_int)})', re.IGNORECASE).search

    if m := ord_search(text.lower()):
        return ordinal_to_int[m.group(1)]
    return None
