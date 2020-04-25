#!/usr/bin/env python

import logging
import sys
from pathlib import Path
from itertools import permutations
from unittest.mock import MagicMock

from ds_tools.test_common import main, TestCaseBase

sys.path.append(Path(__file__).parents[1].joinpath('lib').as_posix())
from music.common import DiscoEntryType
from music.wiki.disco_entry import DiscoEntry

log = logging.getLogger(__name__)


class DiscoEntryTypeTest(TestCaseBase):
    def assertTypeResult(self, expected_type, categories):
        passed = 0
        failed = 0
        for perm in permutations(categories):
            if DiscoEntryType.for_name(perm) is expected_type:
                passed += 1
            else:
                failed += 1

        total = passed + failed
        pct_pass = passed / total if total else 0
        self.assertGreater(passed, 0, f'0 / {total} permutations of {categories=} resulted in {expected_type=}')
        if failed:
            self.fail(f'Only {passed} / {total} ({pct_pass:.2%}) permutations of {categories=} resulted in {expected_type=}')

    def test_most_specific_type(self):
        categories = {'mini albums', 'albums', '2020 mini albums', '2020 releases'}
        self.assertTypeResult(DiscoEntryType.MiniAlbum, categories)

    def test_de_type_from_wiki_sections(self):
        disco_entry = DiscoEntry(MagicMock(), MagicMock(), type_=['Extended plays'])
        self.assertEqual(disco_entry.type, DiscoEntryType.ExtendedPlay)

        disco_entry = DiscoEntry(MagicMock(), MagicMock(), type_=['Singles', 'As lead artist'])
        self.assertEqual(disco_entry.type, DiscoEntryType.Single)

        disco_entry = DiscoEntry(MagicMock(), MagicMock(), type_=['Studio albums'])
        self.assertEqual(disco_entry.type, DiscoEntryType.Album)

        disco_entry = DiscoEntry(MagicMock(), MagicMock(), type_=['Singles','As featured artist'])
        self.assertEqual(disco_entry.type, DiscoEntryType.Feature)

        disco_entry = DiscoEntry(MagicMock(), MagicMock(), type_=['Singles', 'Promotional singles'])
        self.assertEqual(disco_entry.type, DiscoEntryType.Single)


if __name__ == '__main__':
    main()
