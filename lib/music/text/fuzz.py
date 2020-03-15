"""
:author: Doug Skrypa
"""

import logging
import re
from unicodedata import normalize, combining

from fuzzywuzzy import fuzz
from fuzzywuzzy.fuzz import _token_sort as fuzz_token_sort_ratio, _token_set as fuzz_token_set_ratio

__all__ = ['fuzz_process', 'revised_weighted_ratio']
log = logging.getLogger(__name__)


def fuzz_process(text, strip_special=True, space=True):
    """
    Performs the same functions as :func:`full_process<fuzzywuzzy.utils.full_process>`, with some additional steps.
    Consecutive spaces are condensed, and diacritical marks are stripped.  Example::\n
        >>> fuzz_process('Rosé  한')     # Note: there are 2 spaces here
        'rose 한'

    :param str text: A string to be processed
    :param bool strip_special: Strip special characters (defaults to True - set to False to preserve them)
    :param bool space: Whether spaces should be preserved or stripped entirely
    :return str: The processed string
    """
    if not text:
        return text
    try:
        non_letter_non_num_rx = fuzz_process._non_letter_non_num_rx
        ost_rx = fuzz_process._ost_rx
    except AttributeError:
        non_letter_non_num_rx = fuzz_process._non_letter_non_num_rx = re.compile(r'\W')
        ost_rx = fuzz_process._ost_rx = re.compile(r'\sOST(?:$|\s|\)|\])', re.IGNORECASE)

    original = text
    if strip_special:                               # Some titles are only differentiable by special characters
        text = non_letter_non_num_rx.sub(' ', text) # Convert non-letter/numeric characters to spaces
    sp = ' ' if space else ''
    text = sp.join(text.split())                    # Condense sets of consecutive spaces to 1 space (faster than regex)
    text = ost_rx.sub('', text)                     # Remove 'OST' to prevent false positives based only on that
    text = text.lower().strip()                     # Convert to lower case & strip leading/trailing whitespace
    if len(text) == 0:
        text = ' '.join(original.split()).lower().strip()   # In case the text is only non-letter/numeric characters
    # Remove accents and other diacritical marks; composed Hangul and the like stays intact
    text = normalize('NFC', ''.join(c for c in normalize('NFD', text) if not combining(c)))
    return text


def revised_weighted_ratio(p1, p2):
    """
    Return a measure of the sequences' similarity between 0 and 100, using different algorithms.
    **Steps in the order they occur**

    #. Run full_process from utils on both strings
    #. Short circuit if this makes either string empty
    #. Take the ratio of the two processed strings (fuzz.ratio)
    #. Run checks to compare the length of the strings
        * If one of the strings is more than 1.5 times as long as the other use partial_ratio comparisons - scale
          partial results by 0.9 (this makes sure only full results can return 100)
        * If one of the strings is over 8 times as long as the other instead scale by 0.6
    #. Run the other ratio functions
        * if using partial ratio functions call partial_ratio, partial_token_sort_ratio and partial_token_set_ratio
          scale all of these by the ratio based on length
        * otherwise call token_sort_ratio and token_set_ratio
        * all token based comparisons are scaled by 0.95 (on top of any partial scalars)
    #. Take the highest value from these results round it and return it as an integer.
    """
    if not p1 or not p2:
        return 0
    elif p1 == p2:
        return 100

    base = fuzz.ratio(p1, p2)
    lens = (len(p1), len(p2))
    len_ratio = max(lens) / min(lens)
    # if strings are similar length, don't use partials
    try_partial = len_ratio >= 1.5

    # Defaults:
    # fuzz_token_sort_ratio(s1, s2, partial=True, force_ascii=True, full_process=True)
    # fuzz_token_set_ratio(s1, s2, partial=True, force_ascii=True, full_process=True)

    if try_partial:
        # if one string is much much shorter than the other
        if len_ratio > 3:
            partial_scale = .25
        elif len_ratio > 2:
            partial_scale = .45
        elif len_ratio > 1.5:
            partial_scale = .625
        elif len_ratio > 1:
            partial_scale = .75
        else:
            partial_scale = .90

        partial = fuzz.partial_ratio(p1, p2) * partial_scale
        ptsor = fuzz_token_sort_ratio(p1, p2, True, False, False) * .95 * partial_scale
        # ptsor = fuzz.partial_token_sort_ratio(p1, p2, full_process=False) * .95 * partial_scale
        ptser = fuzz_token_set_ratio(p1, p2, True, False, False) * .95 * partial_scale
        # ptser = fuzz.partial_token_set_ratio(p1, p2, full_process=False) * .95 * partial_scale
        # log.debug('{!r}=?={!r}: ratio={}, len_ratio={}, part_ratio={}, tok_sort_ratio={}, tok_set_ratio={}'.format(p1, p2, base, len_ratio, partial, ptsor, ptser))
        return int(round(max(base, partial, ptsor, ptser)))
    else:
        tsor = fuzz_token_sort_ratio(p1, p2, False, False, False) * .95
        # tsor = fuzz.token_sort_ratio(p1, p2, full_process=False) * .95
        tser = fuzz_token_set_ratio(p1, p2, False, False, False) * .95
        # tser = fuzz.token_set_ratio(p1, p2, full_process=False) * .95
        # log.debug('{!r}=?={!r}: ratio={}, len_ratio={}, tok_sort_ratio={}, tok_set_ratio={}'.format(p1, p2, base, len_ratio, tsor, tser))
        return int(round(max(base, tsor, tser)))
