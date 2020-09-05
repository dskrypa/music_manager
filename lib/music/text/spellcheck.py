"""
:author: Doug Skrypa
"""

import logging
import lzma
import pkg_resources
import re
from functools import cached_property
from pathlib import Path

from symspellpy import SymSpell, Verbosity

from ds_tools.core import get_user_cache_dir

__all__ = ['init_sym_spell', 'is_english', 'english_probability']
log = logging.getLogger(__name__)
WORD_FINDER = re.compile(r'(\w+)').finditer


class SpellChecker:
    @cached_property
    def sym_spell(self):
        return init_sym_spell()

    def is_english(self, text: str) -> bool:
        lookup = self.sym_spell.lookup
        for m in WORD_FINDER(text.lower()):
            results = lookup(m.group(), Verbosity.TOP)
            if not results or results[0].distance != 0:
                return False
        return True

    def english_probability(self, text: str):
        """
        Approximate the likelihood that the provided text is English.

        For strings containing multiple words (delimited by spaces), the string is split and each separate word is
        analyzed.  The return value is calculated as the sum of the number of characters that would not need to change
        to make each word match an entry in the dictionary (edit distance) over the total number of word characters.

        :param str text: The text to analyze
        :return float: A value between 0 and 1, inclusive
        """
        words = text.lower().split()
        lookup = self.sym_spell.lookup
        total_dist = 0
        char_count = 0
        for word in words:
            results = lookup(word, Verbosity.TOP)
            char_count += len(word)
            if results:
                total_dist += results[0].distance
            else:
                total_dist += len(word)

        return (char_count - total_dist) / char_count if char_count else 0


spell_checker = SpellChecker()
is_english = spell_checker.is_english
english_probability = spell_checker.english_probability


def init_sym_spell():
    sym_spell = SymSpell(max_dictionary_edit_distance=0, prefix_length=1)

    dict_path_pkl = Path(get_user_cache_dir('music_manager')).joinpath('words.pkl.gz')
    if dict_path_pkl.exists():
        log.debug(f'Loading pickled spellcheck dictionary: {dict_path_pkl}')
        sym_spell.load_pickle(dict_path_pkl)
    else:
        dict_path = pkg_resources.resource_filename('symspellpy', 'frequency_dictionary_en_82_765.txt')
        sym_spell.load_dictionary(dict_path, 0, 1)
        word_list_path_xz = Path(pkg_resources.resource_filename('music', '../../etc/scowl/words.xz')).resolve()
        log.debug(f'Loading default dictionary + word list from {word_list_path_xz}')
        with lzma.open(word_list_path_xz, 'rt', encoding='utf-8') as f:
            word_list = f.read().splitlines()

        loaded = sym_spell._words
        min_count = min(loaded.values())
        add_word = sym_spell.create_dictionary_entry
        for word in word_list:
            try:
                loaded[word]
            except KeyError:
                add_word(word, min_count)

        fmt = 'Saving pickled spellcheck dictionary (this is a one-time action that may take about 15 seconds): {}'
        log.info(fmt.format(dict_path_pkl))
        sym_spell.save_pickle(dict_path_pkl)

    return sym_spell
