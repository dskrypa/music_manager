#!/usr/bin/env python

import logging
import sys
from datetime import date
from pathlib import Path

from ds_tools.test_common import main, TestCaseBase

sys.path.append(Path(__file__).parents[1].joinpath('lib').as_posix())
from music.common.disco_entry import DiscoEntryType
from music.manager.update import AlbumInfo, TrackInfo, normalize_case

log = logging.getLogger(__name__)


class AlbumInfoTest(TestCaseBase):
    def test_entry_type_from_str(self):
        info = AlbumInfo(type='Album')
        self.assertEqual(info.type, DiscoEntryType.Album)

    def test_default_type(self):
        info = AlbumInfo()
        self.assertEqual(info.type, DiscoEntryType.UNKNOWN)

    def test_serialized_type(self):
        info = AlbumInfo()
        info_dict = info.to_dict()
        self.assertNotIn('_type', info_dict)
        self.assertIs(info_dict['type'], None)

    def test_deserialized_type(self):
        info_dict = AlbumInfo().to_dict()
        info_dict['type'] = 'Album'
        info = AlbumInfo.from_dict(info_dict)
        self.assertEqual(info.type, DiscoEntryType.Album)

    def test_set_date_in_init(self):
        info = AlbumInfo(date='2021-01-01')
        self.assertEqual(info.date, date(2021, 1, 1))

    def test_set_date(self):
        info = AlbumInfo()
        info.date = '2021-01-01'
        self.assertEqual(info.date, date(2021, 1, 1))
        info.date = date(2021, 1, 2)
        self.assertEqual(info.date, date(2021, 1, 2))

    def test_serialized_date(self):
        info = AlbumInfo()
        info.date = date(2021, 1, 2)
        info_dict = info.to_dict()
        self.assertEqual(info_dict['date'], '2021-01-02')

    def test_normalize_case(self):
        self.assertEqual('OST', normalize_case('OST'))


if __name__ == '__main__':
    main()
