"""
:author: Doug Skrypa
"""

import logging
import sys
from argparse import ArgumentParser
from unittest import TestCase, main as unittest_main

from ds_tools.logging import init_logging
from ds_tools.output import colored

__all__ = ['NameTestCaseBase', 'main']
log = logging.getLogger(__name__)


def main(*test_classes):
    parser = ArgumentParser('Name Parsing Unit Tests')
    parser.add_argument('--include', '-i', nargs='+', help='Names of test functions to include (default: all)')
    parser.add_argument('--verbose', '-v', action='count', default=0, help='Logging verbosity (can be specified multiple times to increase verbosity)')
    args = parser.parse_args()
    init_logging(args.verbose, log_path=None, names=None)

    argv = [sys.argv[0]]
    if args.include:
        names = {m: f'{cls.__name__}.{m}' for cls in test_classes for m in dir(cls)}
        for method_name in args.include:
            argv.append(names.get(method_name, method_name))

    if args.verbose:
        NameTestCaseBase.maybe_print = print

    try:
        unittest_main(warnings='ignore', verbosity=2, exit=False, argv=argv)
    except KeyboardInterrupt:
        print()


class NameTestCaseBase(TestCase):
    maybe_print = lambda s: None

    def setUp(self):
        self.maybe_print()

    def tearDown(self):
        self.maybe_print()

    def assertIsOrEqual(self, name, attr, expected):
        value = getattr(name, attr)
        found = colored(f'{attr}={value!r}', 'cyan')
        _expected = colored(f'expected={expected!r}', 13)
        msg = f'\nFound Name.{found}; {_expected} - full name:\n{name._full_repr()}'
        if expected is None:
            self.assertIs(value, expected, msg)
        else:
            self.assertEqual(value, expected, msg)

    def assertAll(
            self, name, english=None, _english=None, non_eng=None, korean=None, japanese=None, cjk=None, romanized=None,
            lit_translation=None, extra=None
    ):
        attrs = ('english', '_english', 'non_eng', 'korean', 'japanese', 'cjk', 'romanized', 'lit_translation', 'extra')
        args = (english, _english, non_eng, korean, japanese, cjk, romanized, lit_translation, extra)
        for attr, expected in zip(attrs, args):
            self.assertIsOrEqual(name, attr, expected)
