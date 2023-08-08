#!/usr/bin/env python

from datetime import date
from pathlib import Path
from unittest.mock import Mock
from typing import Collection

from wiki_nodes import WikiPage, as_node

from music.test_common import NameTestCaseBase, main
from music.wiki.album import DiscographyEntry, Soundtrack, Album
from music.wiki.parsing.kpop_fandom import KpopFandomParser
from music.wiki.parsing.wikipedia import EditionFinder as WikipediaEditionFinder

DATA_DIR = Path(__file__).parent.joinpath('data', Path(__file__).stem)

parse_kf_track_name = KpopFandomParser().parse_track_name


def get_data(title: str) -> str:
    path = DATA_DIR.joinpath(f'{title}.wiki')
    return path.read_text('utf-8')


class PageContentTest(NameTestCaseBase):
    _site: str
    _interwiki_map: dict[str, str]
    root: Mock

    def _get_page(self, title: str, categories: Collection[str] = None) -> WikiPage:
        data = get_data(title.replace(' ', '_'))
        return WikiPage(title, self._site, data, categories=categories, interwiki_map=self._interwiki_map)

    def _get_disco_entry(self, title: str, categories: Collection[str] = None) -> DiscographyEntry:
        return DiscographyEntry.from_page(self._get_page(title, categories))


class KpopFandomPageContentTest(PageContentTest):
    _site = 'kpop.fandom.com'
    _interwiki_map = {'w': 'https://community.fandom.com/wiki/$1'}
    root = Mock(site=_site, _interwiki_map=_interwiki_map)

    def test_start_up_ost(self):
        album = self._get_disco_entry('Start-Up OST', ['OST'])
        self.assertIsInstance(album, Soundtrack)
        self.assertEqual(2, len(album.editions))
        for name, edition in zip(('Pre-releases', 'Full OST'), album.editions):
            with self.subTest(name=name, edition=edition):
                if name != 'Pre-releases':
                    self.assertIn(name, str(edition.name))
                self.assertEqual(3, len(edition.parts), f'Unexpected parts={edition.parts}')

        for part in album.editions[1].parts:
            self.assertEqual(3, len(part.tracks))  # TODO: Make sure this has the expected content


class WikipediaPageContentTest(PageContentTest):
    _site = 'en.wikipedia.org'
    _interwiki_map = {}
    root = Mock(site=_site, _interwiki_map=_interwiki_map)

    def test_garbage_album_edition_names(self):
        album = self._get_disco_entry('Garbage (album)', ['1995 debut albums', 'Garbage (band) albums'])
        self.assertIsInstance(album, Album)
        self.assertEqual(3, len(album.editions))
        expected_names = ['Garbage', 'Garbage (Japanese Edition)', 'Garbage (20th Anniversary Deluxe Edition)']
        self.assertListEqual(expected_names, [ed.full_name() for ed in album.editions])

    def test_beautiful_garbage_edition_names(self):
        album = self._get_disco_entry('Beautiful Garbage', ['2001 albums', 'Garbage (band) albums'])
        self.assertIsInstance(album, Album)
        self.assertEqual(5, len(album.editions))
        expected_names = [
            'Beautiful Garbage',
            'Beautiful Garbage (International Enhanced)',
            'Beautiful Garbage (Japanese Edition)',
            'Beautiful Garbage (20th Anniversary Edition)',
            'Beautiful Garbage (20th Anniversary Edition + Bonus Vinyl)',
        ]
        self.assertListEqual(expected_names, [ed.full_name() for ed in album.editions])
        self.assertEqual(1, len(album.editions[0].parts))  # Standard
        self.assertEqual(1, len(album.editions[1].parts))  # International
        self.assertEqual(1, len(album.editions[2].parts))  # Japanese
        self.assertEqual(4, len(album.editions[3].parts))  # 20th Anniversary Edition
        self.assertEqual(5, len(album.editions[4].parts))  # 20th Anniversary Edition + bonus vinyl

    def test_parse_start_date_template(self):
        page = Mock(infobox={'released': as_node('{{Start date|2021|03|19|df=yes}}')})
        finder = WikipediaEditionFinder(Mock(), Mock(), page)
        self.assertEqual({None: date(2021, 3, 19)}, finder.edition_date_map)


if __name__ == '__main__':
    main()
