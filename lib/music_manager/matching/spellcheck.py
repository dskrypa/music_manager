"""
:author: Doug Skrypa
"""

import logging
import lzma
import pkg_resources
from pathlib import Path

from symspellpy import SymSpell, Verbosity

from ds_tools.core import get_user_cache_dir

__all__ = ['init_sym_spell', 'is_english']
log = logging.getLogger(__name__)


def is_english(text):
    try:
        sym_spell = is_english._sym_spell
    except AttributeError:
        sym_spell = is_english._sym_spell = init_sym_spell()

    words = text.lower().split()
    for word in words:
        results = sym_spell.lookup(word, Verbosity.TOP)
        if not results or results[0].distance != 0:
            return False

    return True


def init_sym_spell():
    sym_spell = SymSpell(max_dictionary_edit_distance=0, prefix_length=1)

    dict_path_pkl = Path(get_user_cache_dir('music_manager')).joinpath('words.pkl.gz')
    if dict_path_pkl.exists():
        log.debug(f'Loading pickled spellcheck dictionary: {dict_path_pkl}')
        sym_spell.load_pickle(dict_path_pkl)
    else:
        dict_path = pkg_resources.resource_filename('symspellpy', 'frequency_dictionary_en_82_765.txt')
        sym_spell.load_dictionary(dict_path, 0, 1)
        word_list_path_xz = Path(pkg_resources.resource_filename('music_manager', '../../etc/scowl/words.xz')).resolve()
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
