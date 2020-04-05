"""
:author: Doug Skrypa
"""

import logging
from collections import defaultdict
from itertools import chain
from typing import Tuple, Optional

__all__ = ['parenthesized', 'partition_enclosed', 'split_enclosed', 'ends_with_enclosed', 'strip_enclosed']
log = logging.getLogger(__name__)

OPENERS = '([{~`"\'～“՚՛՜՝“⁽₍⌈⌊〈〈《「『【〔〖〘〚〝〝﹙﹛﹝（［｛｟｢‐‘-<'
CLOSERS = ')]}~`"\'～“՚՛՜՝”⁾₎⌉⌋〉〉》」』】〕〗〙〛〞〟﹚﹜﹞）］｝｠｣‐’->'

class _CharMatcher:
    __slots__ = ('openers', 'closers', 'opener_to_closer')

    """Lazily compute the mapping only after the first request"""
    def __init__(self, openers: str, closers: str):
        self.openers = openers
        self.closers = closers
        self.opener_to_closer = None

    def __contains__(self, item) -> bool:
        try:
            self[item]
        except KeyError:
            return False
        return True

    def __getitem__(self, opener: str) -> str:
        try:
            return self.opener_to_closer[opener]
        except TypeError:
            self.opener_to_closer = o2c = {}
            for a, b in zip(self.openers, self.closers):
                try:
                    o2c[a] += b
                except KeyError:
                    o2c[a] = b
            return self.opener_to_closer[opener]


OPENER_TO_CLOSER = _CharMatcher(OPENERS, CLOSERS)
CLOSER_TO_OPENER = _CharMatcher(CLOSERS, OPENERS)


def ends_with_enclosed(text: str, exclude: Optional[str] = None) -> Optional[str]:
    """
    :param str text: A string to examine
    :param str exclude: If specified, exclude the provided characters from counting as closers
    :return str|None: The opener + closer characters if the string contains enclosed text, otherwise None
    """
    if len(text) < 2:
        return None
    closer = text[-1]
    if exclude and closer in exclude:
        return None
    try:
        openers = CLOSER_TO_OPENER[closer]
    except KeyError:
        return None
    if opener := next((c for c in openers if c in text), None):
        return opener + closer
    return None


def strip_enclosed(text: str) -> str:
    enclosing = ends_with_enclosed(text)
    if enclosing:
        opener, closer = enclosing
        if text.startswith(opener):
            return text[1:-1]
    return text


def split_enclosed(text: str, reverse=False, inner=False, recurse=0, maxsplit=0) -> Tuple[str, ...]:
    """
    Split the provided string to separate substrings that are enclosed in matching quotes / parentheses / etc.  By
    default, the string is traversed from left to right, and outer-most enclosed substrings are extracted when they are
    surrounded by different sets of enclosing characters.  Even with no recursion, the returned tuple may contain more
    than 3 values if the original string contained multiple top-level enclosed substrings.  Enclosed substrings within
    those extracted substrings are only extracted when recursion is enabled.

    :param str text: The string to split.
    :param bool reverse: Traverse the string from right to left instead of left to right.  Does not change the order of
      substrings in the returned tuple.
    :param bool inner: Return inner-most enclosed substrings when they are surrounded by multiple different sets of
      enclosing characters.  Behavior does not change when the substring is enclosed in multiple sets of the same pair
      of enclosing characters.
    :param int recurse: The number of levels to recurse.
    :param int maxsplit: The maximum number of splits to perform.  If < 2, and text exists after the enclosed portion,
      then the enclosed portion will not be extracted - it will be attached to the preceding or succeeding part,
      depending on direction of traversal.
    :return tuple: The split string, with empty values filtered out.  If no enclosed substrings are found, the returned
      tuple will contain the original string.
    """
    # log.debug(f'split_enclosed({text!r}, rev={reverse}, inner={inner}, recurse={recurse}, max={maxsplit})')
    if maxsplit < 1:
        return _split_enclosed(text, reverse, inner, recurse)
    try:
        _text, first_k, i = _partition_enclosed(text, reverse, inner)
    except ValueError:
        # log.debug(f'  > {(text,)}')
        # noinspection PyRedundantParentheses
        return (text,)

    a, b, c = raw = _return_partitioned(_text, first_k, i, reverse)
    parts = tuple(filter(None, raw))
    if maxsplit == 1 and len(parts) > 2:
        opener_idx = first_k - 1
        a, b = _text[:opener_idx].strip(), _text[opener_idx:].strip()
        if reverse:
            a, b = b[::-1], a[::-1]
        parts = (a, b)
        c = None

    maxsplit -= len(parts) - 1
    combined = []
    if a:
        if maxsplit:
            split = split_enclosed(a, reverse, inner, recurse - 1, maxsplit)
            maxsplit -= len(split) - 1
            combined.extend(split)
        else:
            split = split_enclosed(a, reverse, inner, recurse - 1, 1)
            if len(split) == 1:
                combined.extend(split)
            else:
                combined.append(a)
    if b:
        if recurse:
            if maxsplit:
                split = split_enclosed(b, reverse, inner, recurse - 1, maxsplit)
                maxsplit -= len(split) - 1
                combined.extend(split)
            else:
                split = split_enclosed(b, reverse, inner, recurse - 1, 1)
                if len(split) == 1:
                    combined.extend(split)
                else:
                    combined.append(b)
        else:
            combined.append(b)
    if c:
        if maxsplit:
            split = split_enclosed(c, reverse, inner, recurse - 1, maxsplit)
            maxsplit -= len(split) - 1
            combined.extend(split)
        else:
            split = split_enclosed(c, reverse, inner, recurse - 1, 1)
            if len(split) == 1:
                combined.extend(split)
            else:
                combined.append(c)
    # log.debug(f'  > {combined}')
    return tuple(combined)


def _split_enclosed(text: str, reverse=False, inner=False, recurse=0) -> Tuple[str, ...]:
    try:
        a, b, c = partition_enclosed(text, reverse, inner)
    except ValueError:
        # noinspection PyRedundantParentheses
        return (text,)
    if recurse > 0:
        recurse -= 1
        chained = chain(
            _split_enclosed(a, reverse, inner, recurse), _split_enclosed(b, reverse, inner, recurse),
            _split_enclosed(c, reverse, inner, recurse)
        )
    else:
        chained = chain(_split_enclosed(a, reverse, inner), (b,), _split_enclosed(c, reverse, inner))
    return tuple(filter(None, chained))


def partition_enclosed(text: str, reverse=False, inner=False) -> Tuple[str, str, str]:
    """
    Partition the provided string to separate substrings that are enclosed in matching quotes / parentheses / etc.

    :param str text: The string to partition.
    :param bool reverse: Traverse the string from right to left instead of left to right.  Does not change the order of
      substrings in the returned tuple.
    :param bool inner: Return inner-most enclosed substrings when they are surrounded by multiple different sets of
      enclosing characters.  Behavior does not change when the substring is enclosed in multiple sets of the same pair
      of enclosing characters.
    :return tuple: A 3-tuple containing the part before the enclosed substring, the enclosed substring (without the
      enclosing characters), and the part after the enclosed substring.
    :raises: :exc:`ValueError` if no enclosed text is found.
    """
    text, first_k, i = _partition_enclosed(text, reverse, inner)
    return _return_partitioned(text, first_k, i, reverse)


def _partition_enclosed(text: str, reverse=False, inner=False) -> Tuple[str, int, int]:
    """
    Returns the text in case it was reversed, the index of the first character that is enclosed, and the index of the
    closing character for the enclosed portion.
    """
    if reverse:
        o2c, c2o = CLOSER_TO_OPENER, OPENER_TO_CLOSER
        text = text[::-1]
    else:
        o2c, c2o = OPENER_TO_CLOSER, CLOSER_TO_OPENER

    opened = defaultdict(int)
    closed = defaultdict(int)
    first = defaultdict(list)   # Treat as a LIFO queue
    pairs = []
    # log.debug(f'Partitioning enclosed {text=!r}')
    for i, c in enumerate(text):
        # log.debug(f'{i=} {c=!r} ord(c)={ord(c)} first={dict(first)} {pairs=} opened={dict(opened)} closed={dict(closed)}')
        if c in o2c:
            if c in c2o:
                for k in c2o[c]:
                    if opened[k] > closed[k]:
                        closed[k] += 1
                    if opened[k] and opened[k] == closed[k]:
                        first_k = first[k].pop()
                        if inner:
                            return text, first_k, i
                        else:
                            if not first[k]:
                                del first[k]
                            if not first or first_k < min(vals[0] for vals in first.values()):
                                return text, first_k, i
                            else:
                                pairs.append((first_k, i))

            # if not opened[c] or opened[c] == closed[c]:
            if opened[c] == closed[c]:
                first[c].append(i + 1)
            opened[c] += 1
        elif c in c2o:
            for k in c2o[c]:
                if opened[k] > closed[k]:
                    closed[k] += 1
                if opened[k] and opened[k] == closed[k]:
                    first_k = first[k].pop()
                    if inner:
                        return text, first_k, i
                    else:
                        if not first[k]:
                            del first[k]
                        if not first or first_k < min(vals[0] for vals in first.values()):
                            return text, first_k, i
                        else:
                            pairs.append((first_k, i))

    if pairs:
        first_k, i = min(pairs)
        return text, first_k, i

    raise ValueError('No enclosed text found')


def _return_partitioned(text: str, first_k: int, i: int, reverse: bool) -> Tuple[str, str, str]:
    a, b, c = text[:first_k - 1].strip(), text[first_k:i].strip(), text[i + 1:].strip()
    if reverse:
        return c[::-1], b[::-1], a[::-1]
    return a, b, c


def parenthesized(text: str, chars: str = '()') -> str:
    """
    Extract the first enclosed substring from the given string.

    :param str text: A string
    :param str chars: The enclosing characters from which text should be extracted
    :return str: The first substring that was enclosed
    """
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
