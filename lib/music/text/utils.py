"""
:author: Doug Skrypa
"""

from typing import Sequence

__all__ = ['combine_with_parens']


def combine_with_parens(parts: Sequence[str]):
    if len(parts) == 1:
        return parts[0]
    return '{} {}'.format(parts[0], ' '.join(f'({part})' for part in parts[1:]))
