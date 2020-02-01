#!/usr/bin/env python

import logging
import sys
import unittest
from pathlib import Path

sys.path.append(Path(__file__).parents[1].joinpath('lib').as_posix())
from ds_tools.logging import init_logging
from ds_tools.wiki.page import WikiPage
from music_manager.wiki.base import WikiEntity, PersonOrGroup, Agency, SpecialEvent, TVSeries
from music_manager.wiki.artist import Artist, Singer, Group
from music_manager.wiki.album import Discography, SongCollection, SongCollectionPart, Album, Single, Soundtrack
from music_manager.wiki.track import Track
from music_manager.wiki.exceptions import EntityTypeError

log = logging.getLogger(__name__)
ENTITY_TYPES = {
    WikiEntity, PersonOrGroup, Agency, SpecialEvent, TVSeries, Artist, Singer, Group, Discography, SongCollection,
    SongCollectionPart, Album, Single, Soundtrack, Track
}
CATEGORY_COMPATIBLE_TYPE_MAP = {
    'singer': (Singer, {WikiEntity, PersonOrGroup, Artist, Singer}),
    'group': (Group, {WikiEntity, PersonOrGroup, Artist, Group}),
    'discography': (Discography, {WikiEntity, Discography}),
    'album': (Album, {WikiEntity, SongCollection, Album}),
    'single': (Single, {WikiEntity, SongCollection, Single}),
    'soundtrack': (Soundtrack, {WikiEntity, SongCollection, Soundtrack}),
    'agency': (Agency, {WikiEntity, PersonOrGroup, Agency}),
    'competition': (SpecialEvent, {WikiEntity, SpecialEvent}),
    'television program': (TVSeries, {WikiEntity, TVSeries})
}


class WikiEntityCompatibilityTest(unittest.TestCase):
    def setUp(self):
        self.n = 0
        self.expected = 0

    def tearDown(self):
        sys.stdout.write(f'[{self.n}/{self.expected}] ')
        sys.stdout.flush()

    def test_incompatible_types(self):
        for category, (expected_cls, compatible) in CATEGORY_COMPATIBLE_TYPE_MAP.items():
            page = WikiPage('test', None, '', [category])
            incompatible = ENTITY_TYPES.difference(compatible)
            self.expected += len(incompatible)
            for cls in incompatible:
                with self.assertRaises(EntityTypeError):
                    cls.from_page(page)
                self.n += 1

    def test_compatible_types(self):
        for category, (expected_cls, compatible) in CATEGORY_COMPATIBLE_TYPE_MAP.items():
            page = WikiPage('test', None, '', [category])
            self.expected += len(compatible)
            for cls in compatible:
                self.assertIsInstance(cls.from_page(page), expected_cls)
                self.n += 1


if __name__ == '__main__':
    init_logging(0, log_path=None)
    try:
        unittest.main(warnings='ignore', verbosity=2, exit=False)
    except KeyboardInterrupt:
        print()
