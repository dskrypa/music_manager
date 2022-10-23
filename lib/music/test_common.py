"""
:author: Doug Skrypa
"""

from unittest.mock import Mock, MagicMock

from wikitextparser import WikiText

from ds_tools.test_common import TestCaseBase, main
from ds_tools.output import colored

from wiki_nodes import Node, as_node, Root, WikiPage, Section
from wiki_nodes.testing import WikiNodesTest

from .text.name import Name

__all__ = ['NameTestCaseBase', 'main', 'TestCaseBase', 'fake_page']


class NameTestCaseBase(WikiNodesTest):
# class NameTestCaseBase(TestCaseBase):
    _site = None
    _interwiki_map = None

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

    def _fake_page(self, *args, **kwargs):
        return fake_page(*args, site=self._site, _interwiki_map=self._interwiki_map, **kwargs)

    def _make_root(self, page_text, site=None, interwiki_map=None):
        return Root(page_text, site=site or self._site, interwiki_map=interwiki_map or self._interwiki_map)


def _to_set(value):
    if isinstance(value, set):
        return value
    elif isinstance(value, Name):
        return {value}
    else:
        return set(value)


def fake_page(intro, infobox=None, site=None, _interwiki_map=None, title: str = None, client=None, **kwargs):
    # kwargs.setdefault('sections', Mock(find=lambda *a, **kw: None, get=lambda *a, **kw: None))
    # page = Mock(site=site, _interwiki_map=_interwiki_map, raw=Mock(string=intro), **kwargs)
    page = WikiPage(title or 'test', site, '', interwiki_map=_interwiki_map, client=client or Mock(), **kwargs)
    page.raw = MagicMock(string=intro)  # Needs to have iterable members
    page.__dict__['sections'] = Section(WikiText(''), page)

    if not isinstance(intro, Node):
        intro = as_node(intro, root=page)
    if intro is not None:
        page.intro = lambda *a, **kw: intro
    if infobox is not None and not isinstance(infobox, Node):
        infobox = as_node(infobox, root=page)
    if infobox is not None:
        page.__dict__['infobox'] = infobox
    return page
