"""
:author: Doug Skrypa
"""

import logging
from collections import defaultdict
from itertools import chain

__all__ = ['parenthesized', 'partition_parenthesized', 'split_parenthesized']
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


def split_parenthesized(text, reverse=False, outer=False, recurse=0):
    try:
        a, b, c = partition_parenthesized(text, reverse, outer)
    except ValueError:
        # noinspection PyRedundantParentheses
        return (text,)
    if recurse > 0:
        recurse -= 1
        chained = chain(
            split_parenthesized(a, reverse, outer, recurse), split_parenthesized(b, reverse, outer, recurse),
            split_parenthesized(c, reverse, outer, recurse)
        )
    else:
        chained = chain(split_parenthesized(a, reverse, outer), (b,), split_parenthesized(c, reverse, outer))
    return tuple(filter(None, chained))


def partition_parenthesized(text, reverse=False, outer=False):
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
                        if outer:
                            del first[k]
                            if not first or first_k < min(first.values()):
                                return _return_partitioned(text, first_k, i, reverse)
                            else:
                                pairs.append((first_k, i))
                        else:
                            return _return_partitioned(text, first_k, i, reverse)

            if not opened[c]:
                first[c] = i + 1
            opened[c] += 1
        elif c in c2o:
            for k in c2o[c]:
                if opened[k] > closed[k]:
                    closed[k] += 1
                if opened[k] and opened[k] == closed[k]:
                    first_k = first[k]
                    if outer:
                        del first[k]
                        if not first or first_k < min(first.values()):
                            return _return_partitioned(text, first_k, i, reverse)
                        else:
                            pairs.append((first_k, i))
                    else:
                        return _return_partitioned(text, first_k, i, reverse)

    if outer and pairs:
        first_k, i = min(pairs)
        return _return_partitioned(text, first_k, i, reverse)

    raise ValueError('No parenthesized text found')


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
