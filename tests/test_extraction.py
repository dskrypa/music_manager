#!/usr/bin/env python

import logging
import sys
import unittest
from argparse import ArgumentParser
from pathlib import Path

sys.path.append(Path(__file__).parents[1].joinpath('lib').as_posix())
from ds_tools.logging import init_logging
from music_manager.text.extraction import partition_parenthesized

log = logging.getLogger(__name__)
maybe_print = lambda: None


class _CustomTestCase(unittest.TestCase):
    def setUp(self):
        maybe_print()

    def tearDown(self):
        maybe_print()


class ParenthesizedTestCase(_CustomTestCase):
    def test_partition_parenthesized(self):
        cases = {
            'a (b) c': ('a', 'b', 'c'),
            'a - (b) - c': ('a -', 'b', '- c'),
            '"a (b) "c': ('"a', 'b', '"c'),
            '(a (b) "c"': ('(a (b)', 'c', ''),
            ')a (b) "c"': (')a', 'b', '"c"'),
            '"a" b': ('', 'a', 'b'),
            'a "b"': ('a', 'b', ''),
        }
        for case, expected in cases.items():
            self.assertEqual(expected, partition_parenthesized(case))

    def test_spartition_parenthesized_reverse(self):
        cases = {
            'a (b) c': ('a', 'b', 'c'),
            'a - (b) - c': ('a -', 'b', '- c'),
            '"a (b) "c': ('"a', 'b', '"c'),
            '(a (b) "c"': ('(a (b)', 'c', ''),
            ')a (b) "c"': (')a (b)', 'c', ''),
            '"a" b': ('', 'a', 'b'),
            'a "b"': ('a', 'b', ''),
        }
        for case, expected in cases.items():
            self.assertEqual(expected, partition_parenthesized(case, reverse=True))


if __name__ == '__main__':
    parser = ArgumentParser('Unit Tests')
    parser.add_argument('--include', '-i', nargs='+', help='Names of test functions to include (default: all)')
    parser.add_argument('--verbose', '-v', action='count', default=0, help='Logging verbosity (can be specified multiple times to increase verbosity)')
    args = parser.parse_args()
    init_logging(args.verbose, log_path=None, names=None)

    test_classes = ()
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
