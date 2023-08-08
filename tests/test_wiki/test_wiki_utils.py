#!/usr/bin/env python

from music.test_common import main, TestCaseBase
from music.wiki.parsing.utils import replace_lang_abbrev


class MiscUtilsTest(TestCaseBase):
    def test_replace_abbrev_1(self):
        self.assertEqual(replace_lang_abbrev('JP ver.'), 'Japanese ver.')
        self.assertEqual(replace_lang_abbrev('JP'), 'Japanese')
        self.assertEqual(replace_lang_abbrev('test JP'), 'test Japanese')

    def test_replace_abbrev_2(self):
        self.assertEqual(replace_lang_abbrev('broken'), 'broken')
        self.assertEqual(replace_lang_abbrev('test en'), 'test English')


if __name__ == '__main__':
    main()
