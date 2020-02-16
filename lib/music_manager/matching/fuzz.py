"""
:author: Doug Skrypa
"""

import logging
import re
from unicodedata import normalize, combining

__all__ = ['fuzz_process']
log = logging.getLogger(__name__)


def fuzz_process(text, strip_special=True):
    """
    Performs the same functions as :func:`full_process<fuzzywuzzy.utils.full_process>`, with some additional steps.
    Consecutive spaces are condensed, and diacritical marks are stripped.  Example::\n
        >>> fuzz_process('Rosé  한')     # Note: there are 2 spaces here
        'rose 한'

    :param str text: A string to be processed
    :param bool strip_special: Strip special characters (defaults to True - set to False to preserve them)
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
    text = ' '.join(text.split())                   # Condense sets of consecutive spaces to 1 space (faster than regex)
    text = ost_rx.sub('', text)                     # Remove 'OST' to prevent false positives based only on that
    text = text.lower().strip()                     # Convert to lower case & strip leading/trailing whitespace
    if len(text) == 0:
        text = ' '.join(original.split()).lower().strip()   # In case the text is only non-letter/numeric characters
    # Remove accents and other diacritical marks; composed Hangul and the like stays intact
    text = normalize('NFC', ''.join(c for c in normalize('NFD', text) if not combining(c)))
    return text
