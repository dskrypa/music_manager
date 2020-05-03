#!/usr/bin/env python

import logging
import sys
from pathlib import Path

from ds_tools.test_common import main, TestCaseBase

sys.path.append(Path(__file__).parents[1].joinpath('lib').as_posix())
from music.text.extraction import (
    partition_enclosed, split_enclosed, has_unpaired, get_unpaired, ends_with_enclosed, strip_enclosed
)

log = logging.getLogger(__name__)


class MiscExtractionTestCase(TestCaseBase):
    def test_has_unpaired(self):
        cases = {
            '()': False, ')(': True,
            '(a)': False, ')a(': True,
            'a()': False, '()a': False,
            'a)(': True, ')(a': True,
            '())': True, '(()': True,
            '(())': False,
            '(a)b [(c)d-e]': False
        }
        for text, unpaired in cases.items():
            self.assertIs(has_unpaired(text), unpaired, f'Failed for {text=!r}')

    def test_get_unpaired_reverse(self):
        cases = {
            '()': None, ')(': '(',
            '(a)': None, ')a(': '(',
            'a()': None, '()a': None,
            'a)(': '(', ')(a': '(',
            '())': ')', '(()': '(',
            '(())': None,
            '(a)b [(c)d-e]': None
        }
        for text, unpaired in cases.items():
            self.assertEqual(get_unpaired(text, True), unpaired, f'Failed for {text=!r}')

    def test_get_unpaired_forward(self):
        cases = {
            '()': None, ')(': ')',
            '(a)': None, ')a(': ')',
            'a()': None, '()a': None,
            'a)(': ')', ')(a': ')',
            '())': ')', '(()': '(',
            '(())': None,
            '(a)b [(c)d-e]': None
        }
        for text, unpaired in cases.items():
            self.assertEqual(get_unpaired(text, False), unpaired, f'Failed for {text=!r}')

    def test_ends_with_enclosed(self):
        self.assertTrue(ends_with_enclosed("test 'one'"))
        self.assertFalse(ends_with_enclosed("test one'"))
        self.assertFalse(ends_with_enclosed("test 'one"))
        self.assertTrue(ends_with_enclosed("test (one)"))
        self.assertFalse(ends_with_enclosed("test one)"))
        self.assertFalse(ends_with_enclosed("test (one"))

    def test_strip_enclosed(self):
        self.assertEqual(strip_enclosed('"test"'), 'test')
        self.assertEqual(strip_enclosed('"test" a'), '"test" a')
        self.assertEqual(strip_enclosed('a "test"'), 'a "test"')
        self.assertEqual(strip_enclosed('""'), '')
        self.assertEqual(strip_enclosed('"a" b "c"'), 'a" b "c')    # Not ideal... but this is not analyzing closely
        self.assertEqual(strip_enclosed('"a b "c"'), 'a b "c')


class ExtractEnclosedTestCase(TestCaseBase):
    def test_partition_enclosed(self):
        cases = {
            'a (b) c': ('a', 'b', 'c'),
            'a - (b) - c': ('a', '(b)', 'c'),
            '"a (b) "c': ('', 'a (b)', 'c'),
            '(a (b) "c"': ('(a (b)', 'c', ''),
            ')a (b) "c"': (')a', 'b', '"c"'),
            '"a" b': ('', 'a', 'b'),
            'a "b"': ('a', 'b', ''),
            '((a) b) c': ('', '(a) b', 'c'),
        }
        for case, expected in cases.items():
            self.assertEqual(expected, partition_enclosed(case))

    def test_partition_enclosed_reverse(self):
        cases = {
            'a (b) c': ('a', 'b', 'c'),
            'a - (b) - c': ('a', '(b)', 'c'),
            '"a (b) "c': ('', 'a (b)', 'c'),
            '(a (b) "c"': ('(a (b)', 'c', ''),
            ')a (b) "c"': (')a (b)', 'c', ''),
            '"a" b': ('', 'a', 'b'),
            'a "b"': ('a', 'b', ''),
        }
        for case, expected in cases.items():
            self.assertEqual(expected, partition_enclosed(case, reverse=True))

    def test_partition_enclosed_inner(self):
        cases = {
            'a (b) c': ('a', 'b', 'c'),
            'a - (b) - c': ('a -', 'b', '- c'),
            '"a (b) "c': ('"a', 'b', '"c'),
            '(a (b) "c"': ('(a (b)', 'c', ''),
            ')a (b) "c"': (')a', 'b', '"c"'),
            '"a" b': ('', 'a', 'b'),
            'a "b"': ('a', 'b', ''),
            '((a) b) c': ('', '(a) b', 'c'),
        }
        for case, expected in cases.items():
            self.assertEqual(expected, partition_enclosed(case, inner=True))

    def test_split_enclosed(self):
        cases = {
            'a (b) c': ('a', 'b', 'c'),
            'a - (b) - c': ('a', '(b)', 'c'),
            '"a (b) "c': ('a (b)', 'c'),
            '(a (b) "c"': ('(a (b)', 'c'),
            ')a (b) "c"': (')a', 'b', 'c'),
            '"a" b': ('a', 'b'),
            'a "b"': ('a', 'b'),
            '((a) b)': ('(a) b',)
        }
        for case, expected in cases.items():
            self.assertEqual(expected, split_enclosed(case))

    def test_split_enclosed_recurse(self):
        cases = {
            '((a) b)': ('a', 'b'),
            '((a (b)) c)': ('a (b)', 'c'),
            '((a) b) c': ('a', 'b', 'c'),
        }
        for case, expected in cases.items():
            self.assertEqual(expected, split_enclosed(case, recurse=1))

        cases = {
            '((a) b)': ('a', 'b'),
            '((a (b)) c)': ('a', 'b', 'c'),
            '((a) b) c': ('a', 'b', 'c'),
        }
        for case, expected in cases.items():
            self.assertEqual(expected, split_enclosed(case, recurse=2))

    def test_split_enclosed_limit_1(self):
        cases_fwd = {
            'a': ('a',),
            '(a)': ('a',),
            'a (b)': ('a', 'b'),
            'a (b) c': ('a', '(b) c'),
            'a (b) (c)': ('a', '(b) (c)'),
        }
        for case, expected in cases_fwd.items():
            self.assertEqual(expected, split_enclosed(case, maxsplit=1))

        cases_rev = {
            'a': ('a',),
            '(a)': ('a',),
            'a (b)': ('a', 'b'),
            'a (b) c': ('a (b)', 'c'),
            'a (b) (c)': ('a (b)', 'c'),
        }
        for case, expected in cases_rev.items():
            self.assertEqual(expected, split_enclosed(case, maxsplit=1, reverse=True))

    def test_split_enclosed_limit_2(self):
        cases_fwd = {
            'a (b)': ('a', 'b'),
            'a (b) c': ('a', 'b', 'c'),
            'a (b) (c)': ('a', 'b', 'c'),
            '(a) (b) (c)': ('a', 'b', 'c'),
            'a (b) (c) d': ('a', 'b', '(c) d'),
            'a (b) (c) (d)': ('a', 'b', '(c) (d)'),
        }
        for case, expected in cases_fwd.items():
            self.assertEqual(expected, split_enclosed(case, maxsplit=2))

        cases_rev = {
            'a (b)': ('a', 'b'),
            'a (b) c': ('a', 'b', 'c'),
            'a (b) (c)': ('a', 'b', 'c'),
            '(a) (b) (c)': ('a', 'b', 'c'),
            'a (b) (c) d': ('a (b)', 'c', 'd'),
            'a (b) (c) (d)': ('a (b)', 'c', 'd'),
        }
        for case, expected in cases_rev.items():
            self.assertEqual(expected, split_enclosed(case, maxsplit=2, reverse=True))


if __name__ == '__main__':
    main()
