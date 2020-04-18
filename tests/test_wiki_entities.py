#!/usr/bin/env python

import logging
import sys
from pathlib import Path

from ds_tools.test_common import main, TestCaseBase

sys.path.append(Path(__file__).parents[1].joinpath('lib').as_posix())
from wiki_nodes.page import WikiPage
from music.wiki.base import WikiEntity, PersonOrGroup, Agency, SpecialEvent, TVSeries
from music.wiki.artist import Artist, Singer, Group
from music.wiki.album import DiscographyEntry, Album, Single, Soundtrack
from music.wiki.discography import Discography
from music.wiki.exceptions import EntityTypeError

log = logging.getLogger(__name__)
ENTITY_TYPES = {
    WikiEntity, PersonOrGroup, Agency, SpecialEvent, TVSeries, Artist, Singer, Group, Discography, DiscographyEntry,
    Album, Single, Soundtrack
}
CATEGORY_COMPATIBLE_TYPE_MAP = {
    'singer': (Singer, {WikiEntity, PersonOrGroup, Artist, Singer}),
    'group': (Group, {WikiEntity, PersonOrGroup, Artist, Group}),
    'discography': (Discography, {WikiEntity, Discography}),
    'album': (Album, {WikiEntity, DiscographyEntry, Album}),
    'single': (Single, {WikiEntity, DiscographyEntry, Single}),
    'soundtrack': (Soundtrack, {WikiEntity, DiscographyEntry, Soundtrack}),
    'agency': (Agency, {WikiEntity, PersonOrGroup, Agency}),
    'competition': (SpecialEvent, {WikiEntity, SpecialEvent}),
    'television program': (TVSeries, {WikiEntity, TVSeries})
}


class WikiEntityCompatibilityTest(TestCaseBase):
    def setUp(self):
        super().setUp()
        self.n = 0
        self.expected = 0

    def tearDown(self):
        super().tearDown()
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

    def test_tricky_types(self):
        self.expected += 1
        page = WikiPage('test', None, '', ['test artists', 'test group members'])
        self.assertIsInstance(Artist.from_page(page), Singer)
        self.n += 1

    def test_no_category_match(self):
        self.expected += 1
        page = WikiPage('test', None, '', ['test test test'])
        self.assertIs(type(WikiEntity.from_page(page)), WikiEntity)
        self.n += 1
        types = ENTITY_TYPES.difference({WikiEntity})
        self.expected += len(types)
        for cls in types:
            with self.assertRaises(EntityTypeError):
                cls.from_page(page)
            self.n += 1


if __name__ == '__main__':
    main()
