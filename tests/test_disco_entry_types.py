#!/usr/bin/env python

import logging
import sys
from pathlib import Path
from itertools import permutations

from ds_tools.test_common import main, TestCaseBase

sys.path.append(Path(__file__).parents[1].joinpath('lib').as_posix())
from music.common import DiscoEntryType

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


if __name__ == '__main__':
    main()
