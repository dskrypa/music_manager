"""
:author: Doug Skrypa
"""

import logging

from ds_tools.test_common import TestCaseBase, main
from ds_tools.output import colored

__all__ = ['NameTestCaseBase', 'main', 'TestCaseBase']
log = logging.getLogger(__name__)


class NameTestCaseBase(TestCaseBase):
    def assertIsOrEqual(self, name, attr, expected):
        value = getattr(name, attr)
        found = colored(f'{attr}={value!r}', 'cyan')
        _expected = colored(f'expected={expected!r}', 13)
        msg = f'\nFound Name.{found}; {_expected} - full name:\n{name._full_repr()}'
        if expected is None:
            self.assertIs(value, expected, msg)
        elif attr == 'extra' and isinstance(expected, list):
            self.assertSetEqual(set(value), set(expected))
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

    def assertNamesEqual(self, found, expected):
        found = set(found) if not isinstance(found, set) else found
        expected = set(expected) if not isinstance(expected, set) else expected
        try:
            self.assertSetEqual(found, expected)
        except AssertionError:
            error_parts = [
                '',
                colored('Expected: {}'.format('\n'.join(n._full_repr() for n in expected)), 11),
                '~' * 80,
                colored('Found: {}'.format('\n'.join(n._full_repr() for n in found)), 9)
            ]
            raise AssertionError('\n'.join(error_parts)) from None
