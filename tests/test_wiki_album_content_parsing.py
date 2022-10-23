#!/usr/bin/env python

from pathlib import Path
from unittest.mock import MagicMock
from typing import Collection

from wiki_nodes.page import WikiPage
from music.test_common import NameTestCaseBase, main
from music.wiki.album import DiscographyEntry, Soundtrack
from music.wiki.parsing.kpop_fandom import KpopFandomParser

DATA_DIR = Path(__file__).parent.joinpath('data', Path(__file__).stem)

parse_kf_track_name = KpopFandomParser().parse_track_name


def get_data(title: str) -> str:
    path = DATA_DIR.joinpath(f'{title}.wiki')
    return path.read_text('utf-8')


class KpopFandomTrackNameParsingTest(NameTestCaseBase):
    _site = 'kpop.fandom.com'
    _interwiki_map = {'w': 'https://community.fandom.com/wiki/$1'}
    root = MagicMock(site=_site, _interwiki_map=_interwiki_map)

    def _get_page(self, title: str, categories: Collection[str] = None) -> WikiPage:
        data = get_data(title.replace(' ', '_'))
        return WikiPage(title, self._site, data, categories=categories, interwiki_map=self._interwiki_map)

    def test_start_up_ost(self):
        album = DiscographyEntry.from_page(self._get_page('Start-Up OST', ['OST']))
        self.assertIsInstance(album, Soundtrack)
        self.assertEqual(2, len(album.editions))
        for name, edition in zip(('Pre-releases', 'Full OST'), album.editions):
            with self.subTest(name=name, edition=edition):
                if name != 'Pre-releases':
                    self.assertIn(name, str(edition.name))
                self.assertEqual(3, len(edition.parts), f'Unexpected parts={edition.parts}')

        for part in album.editions[1].parts:
            self.assertEqual(3, len(part.tracks))  # TODO: Make sure this has the expected content


if __name__ == '__main__':
    main()
