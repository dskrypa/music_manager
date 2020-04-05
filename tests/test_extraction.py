#!/usr/bin/env python

import logging
import sys
import unittest
from argparse import ArgumentParser
from pathlib import Path

sys.path.append(Path(__file__).parents[1].joinpath('lib').as_posix())
from ds_tools.logging import init_logging
from music.text.extraction import partition_enclosed, split_enclosed, has_unpaired

log = logging.getLogger(__name__)
maybe_print = lambda: None


class _CustomTestCase(unittest.TestCase):
    def setUp(self):
        maybe_print()

    def tearDown(self):
        maybe_print()


class MiscExtractionTestCase(_CustomTestCase):
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


class ExtractEnclosedTestCase(_CustomTestCase):
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
    parser = ArgumentParser('Unit Tests')
    parser.add_argument('--include', '-i', nargs='+', help='Names of test functions to include (default: all)')
    parser.add_argument('--verbose', '-v', action='count', default=0, help='Logging verbosity (can be specified multiple times to increase verbosity)')
    args = parser.parse_args()
    init_logging(args.verbose, log_path=None, names=None)

    test_classes = _CustomTestCase.__subclasses__()
    argv = [sys.argv[0]]
    if args.include:
        names = {m: f'{cls.__name__}.{m}' for cls in test_classes for m in dir(cls)}
        for method_name in args.include:
            argv.append(names.get(method_name, method_name))

    if args.verbose:
        maybe_print = lambda: print()

    try:
        unittest.main(warnings='ignore', verbosity=2, exit=False, argv=argv)
    except KeyboardInterrupt:
        print()
