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
    def __init__(self, main, alt=None, romanized=None, translated=None, versions=None):
        self.main = main
        self.alt = alt
        self._romanized = romanized
        self.translated = translated
        self.versions = versions or []

    @classmethod
    def from_parts(cls, parts):
        if isinstance(parts, str):
            return cls(parts)
        num_parts = len(parts)
        if num_parts < 5:
            return cls(*parts)      # Let lang properties figure it out
        raise ValueError(f'Too many name parts: {parts}')

    def __str__(self):
        eng = self.english
        non_eng = self.non_eng
        if self.eng_is_romanized and non_eng:
            eng = None
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
        if self.non_eng_nospace and other.eng_fuzzed_nospace and self.is_romanized(other.eng_fuzzed_nospace, False):
            scores.append(romanization_match)
        if other.non_eng_nospace and self.eng_fuzzed_nospace and other.is_romanized(self.eng_fuzzed_nospace, False):
            scores.append(romanization_match)
        return scores

    def matches(self, other, threshold=80, agg_func=max, romanization_match=95):
        scores = self._score(other, romanization_match)
        if scores:
            return agg_func(scores) >= threshold
        return False

    @cached_property
    def english(self):
        return self._ver(LangCat.ENG, 'english')

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
    def non_eng(self):
        non_eng = self.korean or self.japanese or self.cjk
        if non_eng:
            return non_eng
        elif self.main and self.main_lang != LangCat.ENG:
            return self.main
        elif self.alt and self.alt_lang != LangCat.ENG:
            return self.alt
        elif self.translated and self.translated_lang != LangCat.ENG:
            return self.translated
        else:
            return None

    @cached_property
    def non_eng_nospace(self):
        non_eng = self.non_eng
        return ''.join(non_eng.split()) if non_eng else None

    @cached_property
    def non_eng_langs(self):
        return LangCat.categorize(self.non_eng, True)

    def is_romanized(self, text, fuzz=True):
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
    def eng_is_romanized(self):
        return self.is_romanized(self.eng_fuzzed_nospace, False)

    @cached_property
    def korean(self):
        return self._ver(LangCat.HAN, 'korean')

    @cached_property
    def japanese(self):
        return self._ver(LangCat.JPN, 'japanese')

    @cached_property
    def cjk(self):
        return self._ver(LangCat.CJK, 'cjk')

    @cached_property
    def main_lang(self):
        return LangCat.categorize(self.main)

    @cached_property
    def main_langs(self):
        lang = self.main_lang
        if lang == LangCat.MIX:
            return LangCat.categorize(self.main, True)
        return {lang}

    @cached_property
    def alt_lang(self):
        return LangCat.categorize(self.alt)

    @cached_property
    def alt_langs(self):
        lang = self.alt_lang
        if lang == LangCat.MIX:
            return LangCat.categorize(self.alt, True)
        return {lang}

    @cached_property
    def translated_lang(self):
        return LangCat.categorize(self.translated)

    @cached_property
    def translated_langs(self):
        lang = self.translated_lang
        if lang == LangCat.MIX:
            return LangCat.categorize(self.translated, True)
        return {lang}

    @cached_property
    def romanized_lang(self):
        return LangCat.categorize(self._romanized)

    @cached_property
    def romanized_langs(self):
        lang = self.romanized_lang
        if lang == LangCat.MIX:
            return LangCat.categorize(self._romanized, True)
        return {lang}

    def _ver(self, lang_cat, attr):
        if self.main_lang == lang_cat:
            return self.main
        elif self.alt_lang == lang_cat:
            return self.alt
        elif self.translated_lang == lang_cat:
            return self.translated
        elif self.romanized_lang == lang_cat:
            return self.romanized
        elif lang_cat != LangCat.ENG:
            if lang_cat in self.main_langs:
                return self.main
            elif lang_cat in self.alt_langs:
                return self.alt
            elif lang_cat in self.translated_langs:
                return self.translated
        return self._from_version(attr)

    def _from_version(self, attr):
        versions = self.versions
        if versions:
            return next(filter(None, (getattr(v, attr) for v in versions)), None)
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
