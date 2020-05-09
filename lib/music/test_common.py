"""
:author: Doug Skrypa
"""

import logging

from ds_tools.test_common import TestCaseBase, main
from ds_tools.output import colored

from wiki_nodes import Node

from .text import Name

__all__ = ['NameTestCaseBase', 'main', 'TestCaseBase']
log = logging.getLogger(__name__)


class NameTestCaseBase(TestCaseBase):
    def assertIsOrEqual(self, name, attr, expected):
        value = getattr(name, attr)
        if isinstance(value, dict) and isinstance(expected, dict):
            raw_found = {k: v.raw.string if isinstance(v, Node) else v for k, v in value.items()}
            raw_expected = {k: v.raw.string if isinstance(v, Node) else v for k, v in expected.items()}
            found = colored(f'{attr}={value!r}\n/ {raw_found}', 'cyan')
            _expected = colored(f'\nexpected={expected!r}\n/ {raw_expected}', 13)
        else:
            found = colored(f'{attr}={value!r}', 'cyan')
            _expected = colored(f'expected={expected!r}', 13)

        name_repr = name.full_repr(delim='\n', indent=4)
        msg = f'\nFound Name.{found}; {_expected} - full name:\n{name_repr}'
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
        if japanese and not cjk:
            cjk = japanese
        attrs = ('english', '_english', 'non_eng', 'korean', 'japanese', 'cjk', 'romanized', 'lit_translation', 'extra')
        args = (english, _english, non_eng, korean, japanese, cjk, romanized, lit_translation, extra)
        # try:
        for attr, expected in zip(attrs, args):
            self.assertIsOrEqual(name, attr, expected)
        # except AssertionError:
        #     name_repr = name.full_repr(delim='\n', indent=4)
        #     attrs = ('eng', 'non_eng', 'romanized', 'lit_translation', 'extra')
        #     args = (_english, non_eng, romanized, lit_translation, extra)
        #     expected = Name(**dict(zip(attrs, args)))
        #     error_parts = [
        #         '', colored(f'Expected: {expected.full_repr()}', 11), '~' * 80,
        #         colored(f'Found: {name_repr}', 9)
        #     ]
        #     raise AssertionError('\n'.join(error_parts)) from None

    def assertNamesEqual(self, found, expected):
        found = _to_set(found)
        expected = _to_set(expected)
        try:
            self.assertSetEqual(found, expected)
        except AssertionError:
            error_parts = [
                '',
                colored('Expected: {}'.format('\n'.join(n.full_repr(delim='\n', indent=4) for n in expected)), 11),
                '~' * 80,
                colored('Found: {}'.format('\n'.join(n.full_repr(delim='\n', indent=4) for n in found)), 9)
            ]
            raise AssertionError('\n'.join(error_parts)) from None


def _to_set(value):
    if isinstance(value, set):
        return value
    elif isinstance(value, Name):
        return {value}
    else:
        return set(value)
