#!/usr/bin/env python

import logging
import sys
from pathlib import Path

sys.path.append(Path(__file__).parents[1].joinpath('lib').as_posix())
from music.text.name import Name
from music.test_common import TestCaseBase, main

log = logging.getLogger(__name__)


class NameMatchingTest(TestCaseBase):
    def test_match_multi_lang_versions(self):
        name = Name(
            'Girls\' Generation', '소녀시대', romanized='So Nyeo Si Dae', versions=[
                Name('SNSD', '소녀시대', romanized='So Nyeo Si Dae'),
                Name('Girls\' Generation', '少女時代', romanized='Shoujo Jidai')
            ]
        )
        self.assertTrue(name.matches('girls generation'))
        self.assertTrue(name.matches('Girls\' Generation'))
        self.assertTrue(name.matches('Girls’ Generation'))
        self.assertTrue(name.matches('소녀시대'))
        self.assertTrue(name.matches('snsd'))
        self.assertTrue(name.matches('SNSD'))
        self.assertTrue(name.matches('s.n.s.d'))
        self.assertTrue(name.matches('So Nyeo Si Dae'))
        self.assertTrue(name.matches('Shoujo Jidai'))
        self.assertTrue(name.matches('少女時代'))
        self.assertTrue(name.matches('Girls\' Generation (SNSD)'))
        self.assertTrue(name.matches('Girls\' Generation (소녀시대)'))
        self.assertTrue(name.matches('Girls\' Generation (少女時代)'))
        self.assertTrue(name.matches('少女時代(SNSD)'))
        self.assertTrue(name.matches('소녀시대(SNSD)'))
        self.assertTrue(name.matches('소녀시대(Girls\' Generation)'))

        self.assertFalse(name.matches('Girls’ Generation-Oh!GG'))
        self.assertFalse(name.matches('소녀시대-Oh!GG'))
        self.assertFalse(name.matches('sns'))


if __name__ == '__main__':
    main()
