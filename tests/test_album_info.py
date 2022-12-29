#!/usr/bin/env python

from datetime import date
from unittest.mock import Mock

from ds_tools.test_common import main, TestCaseBase

from music.common.disco_entry import DiscoEntryType
from music.manager.update import AlbumInfo, TrackInfo, Field, normalize_case, parse_date


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

    # region Date Tests

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

    def test_parse_date_unknown_format(self):
        self.assertIs(None, parse_date('1234567890'))

    # endregion

    def test_normalize_case(self):
        self.assertEqual('OST', normalize_case('OST'))

    def test_field_returns_self_on_class(self):
        self.assertIsInstance(TrackInfo.title, Field)

    def test_invalid_field(self):
        with self.assertRaisesRegex(KeyError, "Invalid TrackInfo keys/attributes: 'foo', 'bar'"):
            TrackInfo(None, title='baz', foo='123', bar=456)  # noqa

    # region TrackInfo Tests

    def test_track_as_dict_sparse(self):
        track = TrackInfo(Mock(), title='foo')
        expected = {
            'title': 'foo', 'artist': None, 'num': None, 'name': None, 'genre': [], 'rating': None, 'disk': None
        }
        self.assertDictEqual(expected, track.to_dict())
        expected['title'] = 'Foo'
        self.assertDictEqual(expected, track.to_dict(True))

    def test_track_as_dict_genre(self):
        self.assertEqual(['foo'], TrackInfo(Mock(), title='foo', genre='foo').to_dict()['genre'])
        track = TrackInfo(Mock(), title='foo', genre=['foo', 'bar', 'foo'])
        self.assertEqual(['bar', 'foo'], track.to_dict()['genre'])
        self.assertEqual(['Bar', 'Foo'], track.to_dict(True)['genre'])

    def test_track_add_genre(self):
        track = TrackInfo(Mock(), title='foo', genre='foo')
        track.add_genre('bar')
        self.assertEqual(['bar', 'foo'], track.to_dict()['genre'])

    # endregion

    def test_album_type(self):
        self.assertEqual(DiscoEntryType.UNKNOWN, AlbumInfo().type)
        self.assertEqual(DiscoEntryType.UNKNOWN, AlbumInfo(type='foo').type)
        self.assertEqual(DiscoEntryType.UNKNOWN, AlbumInfo(type=None).type)
        self.assertEqual(DiscoEntryType.UNKNOWN, AlbumInfo(type=DiscoEntryType.UNKNOWN).type)
        self.assertEqual(DiscoEntryType.Album, AlbumInfo(type='album').type)
        self.assertIs(None, AlbumInfo(type=DiscoEntryType.UNKNOWN).to_dict()['type'])

    def test_album_ost(self):
        self.assertTrue(AlbumInfo(type='ost').ost)
        self.assertFalse(AlbumInfo(type='album').ost)
        self.assertFalse(AlbumInfo().ost)


if __name__ == '__main__':
    main()
