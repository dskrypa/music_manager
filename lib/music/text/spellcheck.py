"""
:author: Doug Skrypa
"""

from __future__ import annotations

import logging
from functools import cached_property
from typing import TYPE_CHECKING, Callable, Iterator, Match

if TYPE_CHECKING:
    from symspellpy import Verbosity, SymSpell

__all__ = ['init_sym_spell', 'is_english', 'english_probability']
log = logging.getLogger(__name__)


class SpellChecker:
    @cached_property
    def sym_spell(self) -> SymSpell:
        return init_sym_spell()

    @cached_property
    def _verbosity(self) -> Verbosity:
        from symspellpy import Verbosity

        return Verbosity.TOP

    @cached_property
    def word_finder(self) -> Callable[[str], Iterator[Match]]:
        import re

        return re.compile(r'(\w+)').finditer

    def is_english(self, text: str) -> bool:
        lookup = self.sym_spell.lookup
        verbosity = self._verbosity
        for m in self.word_finder(text.lower()):
            results = lookup(m.group(), verbosity)
            if not results or results[0].distance != 0:
                return False
        return True

    def english_probability(self, text: str) -> float:
        """
        Approximate the likelihood that the provided text is English.

        For strings containing multiple words (delimited by spaces), the string is split and each separate word is
        analyzed.  The return value is calculated as the sum of the number of characters that would not need to change
        to make each word match an entry in the dictionary (edit distance) over the total number of word characters.

        :param text: The text to analyze
        :return: A value between 0 and 1, inclusive
        """
        words = text.lower().split()
        lookup = self.sym_spell.lookup
        verbosity = self._verbosity
        total_dist = 0
        char_count = 0
        for word in words:
            results = lookup(word, verbosity)
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
    from pathlib import Path
    from symspellpy import SymSpell
    from ds_tools.fs.paths import get_user_cache_dir

    sym_spell = SymSpell(max_dictionary_edit_distance=0, prefix_length=1)
    if (cached_path := Path(get_user_cache_dir('music_manager')).joinpath('words.pkl.gz')).exists():
        log.debug(f'Loading pickled spellcheck dictionary: {cached_path.as_posix()}')
        sym_spell.load_pickle(cached_path)
        return sym_spell

    import lzma
    from importlib.resources import files

    sym_spell.load_dictionary(files('symspellpy').joinpath('frequency_dictionary_en_82_765.txt'), 0, 1)  # noqa

    word_list_path_xz = files('music.text._data.scowl').joinpath('words.xz')
    log.debug(f'Loading default dictionary + word list from {word_list_path_xz.as_posix()}')  # noqa
    with lzma.open(word_list_path_xz, 'rt', encoding='utf-8') as f:  # noqa
        word_list: list[str] = f.read().splitlines()  # noqa

    loaded = sym_spell.words
    min_count = min(loaded.values())
    add_word = sym_spell.create_dictionary_entry
    for word in word_list:
        try:
            loaded[word]
        except KeyError:
            add_word(word, min_count)

    log.info(
        f'Saving cached spellcheck dictionary (this is a one-time action that may take ~15s): {cached_path.as_posix()}'
    )
    sym_spell.save_pickle(cached_path)
    return sym_spell
