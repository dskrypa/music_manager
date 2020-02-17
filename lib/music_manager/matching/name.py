"""
:author: Doug Skrypa
"""

import logging

from ds_tools.compat import cached_property
from ds_tools.unicode.hangul import hangul_romanized_permutations_pattern
from ds_tools.unicode.languages import LangCat, J2R
from .fuzz import fuzz_process, revised_weighted_ratio

__all__ = ['Name']
log = logging.getLogger(__name__)


class Name:
    def __init__(self, eng=None, non_eng=None, romanized=None, lit_translation=None, versions=None, extra=None):
        self._english = eng
        self.non_eng = non_eng
        self.romanized = romanized
        self.lit_translation = lit_translation
        self.versions = versions or []
        self.extra = extra

    def __repr__(self):
        parts = (self.english, self.non_eng, self.romanized, self.lit_translation, self.extra)
        parts = ', '.join(map(repr, filter(None, parts)))
        return f'<{type(self).__name__}({parts})>'

    def __str__(self):
        eng = self.english
        non_eng = self.non_eng
        if eng and non_eng:
            return f'{eng} ({non_eng})'
        return eng or non_eng

    def _score(self, other, romanization_match=95):
        if isinstance(other, str):
            other = Name(other)
        scores = []
        if self.non_eng_nospace and other.non_eng_nospace and self.non_eng_langs == other.non_eng_langs:
            scores.append(revised_weighted_ratio(self.non_eng_nospace, other.non_eng_nospace))
        if self.eng_fuzzed_nospace and other.eng_fuzzed_nospace:
            scores.append(revised_weighted_ratio(self.eng_fuzzed_nospace, other.eng_fuzzed_nospace))
        if self.non_eng_nospace and other.eng_fuzzed_nospace and self.has_romanization(other.eng_fuzzed_nospace, False):
            scores.append(romanization_match)
        if other.non_eng_nospace and self.eng_fuzzed_nospace and other.has_romanization(self.eng_fuzzed_nospace, False):
            scores.append(romanization_match)
        return scores

    def matches(self, other, threshold=80, agg_func=max, romanization_match=95):
        scores = self._score(other, romanization_match)
        if scores:
            return agg_func(scores) >= threshold
        return False

    @cached_property
    def english(self):
        return self._english or self.lit_translation

    @cached_property
    def eng_lower(self):
        eng = self.english
        return eng.lower() if eng else None

    @cached_property
    def eng_fuzzed(self):
        return fuzz_process(self.english)

    @cached_property
    def eng_fuzzed_nospace(self):
        fuzzed = self.eng_fuzzed
        return ''.join(fuzzed.split()) if fuzzed else None

    @cached_property
    def non_eng_nospace(self):
        non_eng = self.non_eng
        return ''.join(non_eng.split()) if non_eng else None

    @cached_property
    def non_eng_lang(self):
        return LangCat.categorize(self.non_eng)

    @cached_property
    def non_eng_langs(self):
        return LangCat.categorize(self.non_eng, True)

    def has_romanization(self, text, fuzz=True):
        """
        :param str text: A string that may be a romanized version of this Name's non-english component
        :param bool fuzz: Whether the given text needs to be fuzzed before attempting to compare it
        :return bool: True if the given text is a romanized version of this Name's non-english component
        """
        fuzzed = fuzz_process(text, space=False) if fuzz else text
        if not fuzzed:
            return False
        if self.korean:
            if self._romanization_pattern.match(fuzzed):
                return True
        other = self.japanese or self.cjk
        if other:
            return fuzzed in self._romanizations
        return False

    @cached_property
    def korean(self):
        non_eng_lang = self.non_eng_lang
        expected = LangCat.HAN
        if non_eng_lang == expected or non_eng_lang == LangCat.MIX and expected in self.non_eng_langs:
            return self.non_eng
        return None

    @cached_property
    def japanese(self):
        non_eng_lang = self.non_eng_lang
        expected = LangCat.JPN
        if non_eng_lang == expected or non_eng_lang == LangCat.MIX and expected in self.non_eng_langs:
            return self.non_eng
        return None

    @cached_property
    def cjk(self):
        non_eng_lang = self.non_eng_lang
        expected = LangCat.CJK
        if non_eng_lang == expected or non_eng_lang == LangCat.MIX and expected in self.non_eng_langs:
            return self.non_eng
        return None

    @cached_property
    def _romanization_pattern(self):
        return hangul_romanized_permutations_pattern(self.korean, False)

    @cached_property
    def _romanizations(self):
        text = self.japanese or self.cjk
        if text:
            return [j2r.romanize(text) for j2r in J2R.romanizers(False)]
        return []
