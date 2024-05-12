"""
:author: Doug Skrypa
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from itertools import chain
from typing import TYPE_CHECKING, Optional, Literal, overload

if TYPE_CHECKING:
    from music.typing import Bool

__all__ = [
    'extract_enclosed', 'partition_enclosed', 'split_enclosed', 'ends_with_enclosed', 'strip_enclosed', 'has_unpaired',
    'get_unpaired', 'strip_unpaired', 'is_enclosed'
]
log = logging.getLogger(__name__)

OPENERS = '([{~`"\'～“՚՛՜՝“⁽₍⌈⌊〈〈《「『【〔〖〘〚〝〝﹙﹛﹝（［｛｟｢‐‘-<'
CLOSERS = ')]}~`"\'～“՚՛՜՝”⁾₎⌉⌋〉〉》」』】〕〗〙〛〞〟﹚﹜﹞）］｝｠｣‐’->'
DASH_CHARS = '~‐-'
QUOTE_CHARS = '`"\'“՚՛՜՝”〞〟〝’'
_NotSet = object()


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


def has_unpaired(text: str, reverse: bool = True, exclude=_NotSet) -> bool:
    return bool(get_unpaired(text, reverse, exclude))


def get_unpaired(text: str, reverse: bool = True, exclude=_NotSet) -> Optional[str]:
    if (i := _get_unpaired(text, reverse, exclude)) is not None:
        return text[i]
    return None


def _get_unpaired(text: str, reverse: bool = True, exclude=_NotSet) -> Optional[int]:
    exclude = DASH_CHARS if exclude is _NotSet else '' if exclude is None else exclude
    if reverse:
        o2c, c2o = CLOSER_TO_OPENER, OPENER_TO_CLOSER
        text = text[::-1]
    else:
        o2c, c2o = OPENER_TO_CLOSER, CLOSER_TO_OPENER

    opened = defaultdict(int)
    closed = defaultdict(int)
    pairs = []
    last = defaultdict(list)
    for i, c in enumerate(text):
        _open = True
        if c in o2c:
            # if c in "'-" and _should_skip(c, text, i, reverse):
            #     continue
            if c in c2o:
                for k in c2o[c]:
                    if opened[k] > closed[k]:
                        _open = False
                        pairs.append((i, last[k].pop()))
                        closed[k] += 1
            if _open:
                opened[c] += 1
                last[c].append(i)
        elif c in c2o:
            for k in c2o[c]:
                if opened[k] > closed[k]:
                    pairs.append((i, last[k].pop()))
                    closed[k] += 1
                elif k not in exclude:
                    last[c].append(i)
                    break

    last = {k: v[0] for k, v in last.items() if v and k not in exclude}
    if last:
        i = min(last.values())
        if reverse:
            i = len(text) - 1 - i
        # log.debug(f'{text=} contains enclosing {pairs=} with unclosed={last} => {i} / {text[i]!r}')
        return i
    return None


def ends_with_enclosed(text: str, exclude: str = None) -> Optional[str]:
    """
    :param text: A string to examine
    :param exclude: If specified, exclude the provided characters from counting as closers
    :return: The opener + closer characters if the string contains enclosed text, otherwise None
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
    remainder = text[:-1]
    if opener := next((c for c in openers if c in remainder), None):
        return opener + closer
    return None


def strip_enclosed(text: str, unpaired: bool = False, exclude: str = None) -> str:
    """
    If the given string is fully enclosed, i.e., its first and last characters are a matching pair of opener and closer
    characters as defined above, then those characters will be stripped from the returned string.  If the first and last
    characters are not a matching pair, then no action will be taken.

    :param text: A string
    :param unpaired: Also strip unpaired enclosing characters
    :param exclude: If specified, exclude the provided characters from counting as closers
    :return: The string without the enclosing characters
    """
    if enclosing := ends_with_enclosed(text, exclude):
        opener, closer = enclosing
        if text.startswith(opener):
            return text[1:-1].strip()

    if unpaired:
        return strip_unpaired(text)
    return text


def strip_unpaired(text: str, reverse: bool = False, exclude=_NotSet) -> str:
    if (i := _get_unpaired(text, reverse, exclude)) is not None:
        if i == 0:
            return text[1:].strip()
        elif i == len(text) - 1:
            return text[:-1].strip()
    return text


@overload
def split_enclosed(
    text: str, reverse: bool = False, inner: bool = False, recurse: int = 0, maxsplit: Literal[1] = 0
) -> tuple[str, str] | tuple[str]:
    ...


@overload
def split_enclosed(
    text: str, reverse: bool = False, inner: bool = False, recurse: int = 0, maxsplit: Literal[2] = 0
) -> tuple[str, str, str] | tuple[str, str] | tuple[str]:
    ...


def split_enclosed(
    text: str, reverse: bool = False, inner: bool = False, recurse: int = 0, maxsplit: int = 0
) -> tuple[str, ...]:
    """
    Split the provided string to separate substrings that are enclosed in matching quotes / parentheses / etc.  By
    default, the string is traversed from left to right, and outer-most enclosed substrings are extracted when they are
    surrounded by different sets of enclosing characters.  Even with no recursion, the returned tuple may contain more
    than 3 values if the original string contained multiple top-level enclosed substrings.  Enclosed substrings within
    those extracted substrings are only extracted when recursion is enabled.

    :param text: The string to split.
    :param reverse: Traverse the string from right to left instead of left to right.  Does not change the order of
      substrings in the returned tuple.
    :param inner: Return inner-most enclosed substrings when they are surrounded by multiple different sets of
      enclosing characters.  Behavior does not change when the substring is enclosed in multiple sets of the same pair
      of enclosing characters.
    :param recurse: The number of levels to recurse.
    :param maxsplit: The maximum number of splits to perform.  If < 2, and text exists after the enclosed portion,
      then the enclosed portion will not be extracted - it will be attached to the preceding or succeeding part,
      depending on direction of traversal.
    :return: The split string, with empty values filtered out.  If no enclosed substrings are found, the returned
      tuple will contain the original string.
    """
    # log.debug(f'split_enclosed({text!r}, rev={reverse}, inner={inner}, recurse={recurse}, max={maxsplit})')
    if maxsplit < 1:
        return _split_enclosed(text, reverse, inner, recurse)
    try:
        _text, first_k, i = _partition_enclosed(text, reverse, inner)
    except ValueError:
        # log.debug(f'  > {(text,)}')
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
    for part, do_split in ((a, True), (b, recurse), (c, True)):
        if not part:
            continue
        elif do_split:
            if maxsplit:
                split = split_enclosed(part, reverse, inner, recurse - 1, maxsplit)
                maxsplit -= len(split) - 1
                combined.extend(split)
            else:
                split = split_enclosed(part, reverse, inner, recurse - 1, 1)
                if len(split) == 1:
                    combined.extend(split)
                else:
                    combined.append(part)
        else:
            combined.append(part)

    # log.debug(f'  > {combined}')
    return tuple(combined)


def _split_enclosed(text: str, reverse: bool = False, inner: bool = False, recurse: int = 0) -> tuple[str, ...]:
    try:
        a, b, c = partition_enclosed(text, reverse, inner)
    except ValueError:
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


def partition_enclosed(text: str, reverse: bool = False, inner: bool = False) -> tuple[str, str, str]:
    """
    Partition the provided string to separate substrings that are enclosed in matching quotes / parentheses / etc.

    :param text: The string to partition.
    :param reverse: Traverse the string from right to left instead of left to right.  Does not change the order of
      substrings in the returned tuple.
    :param inner: Return inner-most enclosed substrings when they are surrounded by multiple different sets of
      enclosing characters.  Behavior does not change when the substring is enclosed in multiple sets of the same pair
      of enclosing characters.
    :return: A 3-tuple containing the part before the enclosed substring, the enclosed substring (without the
      enclosing characters), and the part after the enclosed substring.
    :raises: :exc:`ValueError` if no enclosed text is found.
    """
    text, first_k, i = _partition_enclosed(text, reverse, inner)
    return _return_partitioned(text, first_k, i, reverse)


def _partition_enclosed(text: str, reverse: bool = False, inner: bool = False) -> tuple[str, int, int]:
    """
    Returns the text in case it was reversed, the index of the first character that is enclosed, and the index of the
    closing character for the enclosed portion.
    """
    if reverse:
        opener_to_closer_map, closer_to_opener_map = CLOSER_TO_OPENER, OPENER_TO_CLOSER
        text = text[::-1]
    else:
        opener_to_closer_map, closer_to_opener_map = OPENER_TO_CLOSER, CLOSER_TO_OPENER

    opened = defaultdict(int)
    closed = defaultdict(int)
    first = defaultdict(list)   # Treat as a LIFO queue
    pairs = []
    # log.debug(f'Partitioning enclosed {text=}')
    for i, c in enumerate(text):
        # log.debug(f'{i=} {c=} ={ord(c)=} first={dict(first)} {pairs=} opened={dict(opened)} closed={dict(closed)}')
        try:
            openers = closer_to_opener_map[c]
        except KeyError:
            pass
        else:
            if c in "'-" and _should_skip(c, text, i, reverse):
                continue

            for opener in openers:
                if opened[opener] > closed[opener]:
                    closed[opener] += 1
                if opened[opener] == closed[opener] != 0:
                    first_k = first[opener].pop()
                    if inner:
                        return text, first_k, i
                    else:
                        if not first[opener]:
                            del first[opener]
                        if not first or first_k < min(vals[0] for vals in first.values()):
                            return text, first_k, i
                        else:
                            pairs.append((first_k, i))

        if c in opener_to_closer_map:
            if opened[c] == closed[c]:
                first[c].append(i + 1)
            opened[c] += 1

    if pairs:
        first_k, i = min(pairs)
        return text, first_k, i

    raise ValueError('No enclosed text found')


def _should_skip(char: str, text: str, index: int, reverse: bool) -> Bool:
    try:
        skip_matches = _should_skip.skip_matches
    except AttributeError:
        _should_skip.skip_matches = skip_matches = {
            # '-': re.compile(r'^\w-\w', re.IGNORECASE).match,  # TODO: This does produce a desirable split sometimes
            "'": re.compile(r"^(?:\S's\b|\w'\w)", re.IGNORECASE).match,
        }

    try:
        skip_match = skip_matches[char]
    except KeyError:
        return False

    if reverse:
        start = index + 1
        end = index - 2
        to_check = text[start:end][::-1]
    else:
        start = index - 1
        end = index + 2
        to_check = text[start:end]

    return skip_match(to_check)


def _return_partitioned(text: str, first_k: int, i: int, reverse: bool) -> tuple[str, str, str]:
    a, b, c = text[:first_k - 1].strip(), text[first_k:i].strip(), text[i + 1:].strip()
    if reverse:
        return c[::-1], b[::-1], a[::-1]
    return a, b, c


def extract_enclosed(text: str, chars: str = '()') -> str:
    """
    Extract the first enclosed substring from the given string.

    :param text: A string
    :param chars: The enclosing characters from which text should be extracted
    :return: The first substring that was enclosed
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


def is_enclosed(text: str, chars: str = '()') -> bool:
    opener, closer = chars
    if not text:
        return False

    return text[0] == opener and text[-1] == closer
