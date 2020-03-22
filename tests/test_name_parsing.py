#!/usr/bin/env python

import logging
import sys
from pathlib import Path

sys.path.append(Path(__file__).parents[1].joinpath('lib').as_posix())
from music.text.name import Name
from music.test_common import NameTestCaseBase, main

log = logging.getLogger(__name__)


class NameParsingTest(NameTestCaseBase):
    def test_from_parens_basic(self):
        name = Name.from_enclosed('Taeyeon (태연)')
        self.assertAll(name, _english='Taeyeon', english='Taeyeon', non_eng='태연', korean='태연')

    def test_from_parens_with_nested(self):
        name = Name.from_enclosed('(G)I-DLE ((여자)아이들)')
        self.assertAll(name, '(G)I-DLE', '(G)I-DLE', '(여자)아이들', '(여자)아이들')

    def test_match_on_non_eng(self):
        name_1 = Name(non_eng='알고 싶어', lit_translation='I Want to Know')
        name_2 = Name('What\'s in Your House?', '알고 싶어')
        self.assertTrue(name_1.matches(name_2))
        self.assertTrue(name_2.matches(name_1))

    def test_name_part_reset(self):
        name = Name('foo')
        self.assertEqual(name._english, 'foo')
        self.assertEqual(name.english, 'foo')
        name._english = 'bar'
        self.assertEqual(name._english, 'bar')
        self.assertEqual(name.english, 'bar')

    def test_name_part_reset_via_setattr(self):
        name = Name('foo')
        self.assertEqual(name._english, 'foo')
        self.assertEqual(name.english, 'foo')
        setattr(name, '_english', 'bar')
        self.assertEqual(name._english, 'bar')
        self.assertEqual(name.english, 'bar')


if __name__ == '__main__':
    main(NameParsingTest)
