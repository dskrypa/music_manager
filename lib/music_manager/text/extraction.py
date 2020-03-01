"""
:author: Doug Skrypa
"""

import logging
from collections import defaultdict
from itertools import chain

__all__ = ['parenthesized', 'partition_enclosed', 'split_enclosed']
log = logging.getLogger(__name__)

OPENERS = '([{~`"\'～“՚՛՜՝“⁽₍⌈⌊〈〈《「『【〔〖〘〚〝〝﹙﹛﹝（［｛｟｢‐‘-'
CLOSERS = ')]}~`"\'～“՚՛՜՝”⁾₎⌉⌋〉〉》」』】〕〗〙〛〞〟﹚﹜﹞）］｝｠｣‐’-'

class _CharMatcher:
    """Lazily compute the mapping only after the first request"""
    def __init__(self, openers, closers):
        self.openers = openers
        self.closers = closers
        self.opener_to_closer = None

    def __contains__(self, item):
        try:
            self[item]
        except KeyError:
            return False
        return True

    def __getitem__(self, opener):
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


def split_enclosed(text, reverse=False, inner=False, recurse=0):
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
    :return tuple: The split string, with empty values filtered out.  If no enclosed substrings are found, the returned
      tuple will contain the original string.
    """
    try:
        a, b, c = partition_enclosed(text, reverse, inner)
    except ValueError:
        # noinspection PyRedundantParentheses
        return (text,)
    if recurse > 0:
        recurse -= 1
        chained = chain(
            split_enclosed(a, reverse, inner, recurse), split_enclosed(b, reverse, inner, recurse),
            split_enclosed(c, reverse, inner, recurse)
        )
    else:
        chained = chain(split_enclosed(a, reverse, inner), (b,), split_enclosed(c, reverse, inner))
    return tuple(filter(None, chained))


def partition_enclosed(text, reverse=False, inner=False):
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
    if reverse:
        o2c, c2o = CLOSER_TO_OPENER, OPENER_TO_CLOSER
        text = text[::-1]
    else:
        o2c, c2o = OPENER_TO_CLOSER, CLOSER_TO_OPENER

    opened = defaultdict(int)
    closed = defaultdict(int)
    first = {}
    pairs = []
    for i, c in enumerate(text):
        if c in o2c:
            if c in c2o:
                for k in c2o[c]:
                    if opened[k] > closed[k]:
                        closed[k] += 1
                    if opened[k] and opened[k] == closed[k]:
                        first_k = first[k]
                        if inner:
                            return _return_partitioned(text, first_k, i, reverse)
                        else:
                            del first[k]
                            if not first or first_k < min(first.values()):
                                return _return_partitioned(text, first_k, i, reverse)
                            else:
                                pairs.append((first_k, i))

            if not opened[c]:
                first[c] = i + 1
            opened[c] += 1
        elif c in c2o:
            for k in c2o[c]:
                if opened[k] > closed[k]:
                    closed[k] += 1
                if opened[k] and opened[k] == closed[k]:
                    first_k = first[k]
                    if inner:
                        return _return_partitioned(text, first_k, i, reverse)
                    else:
                        del first[k]
                        if not first or first_k < min(first.values()):
                            return _return_partitioned(text, first_k, i, reverse)
                        else:
                            pairs.append((first_k, i))

    if pairs:
        first_k, i = min(pairs)
        return _return_partitioned(text, first_k, i, reverse)

    raise ValueError('No enclosed text found')


def _return_partitioned(text, first_k, i, reverse):
    a, b, c = text[:first_k - 1].strip(), text[first_k:i].strip(), text[i + 1:].strip()
    if reverse:
        return c[::-1], b[::-1], a[::-1]
    return a, b, c


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
