"""
:author: Doug Skrypa
"""

import logging

__all__ = ['parenthesized', 'split_parenthesized']
log = logging.getLogger(__name__)


def split_parenthesized(text, chars='()'):
    text = text.strip()
    if not text.endswith(chars[1]):
        raise ValueError(f'split_parenthesized requires the given text to end in parentheses - found: {text!r}')
    paren_part = parenthesized(text[::-1], chars[::-1])[::-1]
    from_end = len(paren_part) + 2
    first_part = text[:-from_end].strip()
    return first_part, paren_part


def parenthesized(text, chars='()'):
    opener, closer = chars
    opened = 0
    closed = 0
    first = 0

    for i, c in enumerate(text):
        if c == opener:
            if not opened:
                first = i + 1
            opened += 1
        elif c == closer:
            if opened > closed:
                closed += 1
            if opened and opened == closed:
                return text[first:i].strip('\'" ')

    return text
