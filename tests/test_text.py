#!/usr/bin/env python

from music.text.fuzz import fuzz_process, revised_weighted_ratio
from music.text.utils import combine_with_parens
from music.test_common import NameTestCaseBase, main


class TextTest(NameTestCaseBase):
    def test_combine_with_parens(self):
        self.assertEqual('abc', combine_with_parens('abc'))
        self.assertEqual('abc', combine_with_parens(['abc']))
        self.assertEqual('a (b)', combine_with_parens(['a', 'b']))
        self.assertEqual('a (b) (c)', combine_with_parens({'c', 'a', 'b'}))

    def test_fuzz_keep_special(self):
        self.assertEqual('foo', fuzz_process('foo$'))
        self.assertEqual('foo$', fuzz_process('foo$', strip_special=False))
        self.assertEqual('! @ # $%', fuzz_process('! @\n#   $%'))

    def test_revised_weighted_ratio(self):
        self.assertEqual(0, revised_weighted_ratio('', ''))
        self.assertEqual(25, revised_weighted_ratio('a', 'abcdefg'))




if __name__ == '__main__':
    main()
