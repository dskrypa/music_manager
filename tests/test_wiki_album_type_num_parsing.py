#!/usr/bin/env python

import logging
import sys
from pathlib import Path

sys.path.append(Path(__file__).parents[1].joinpath('lib').as_posix())
from wiki_nodes.page import WikiPage
from music.wiki.parsing.generasia import GenerasiaParser
from music.test_common import NameTestCaseBase, main

log = logging.getLogger(__name__)

parse_generasia_album_number = GenerasiaParser.parse_album_number


def page_with_info(info):
    return WikiPage('test', 'www.generasia.com', f'=Information=\n{info}', [])


class GenerasiaAlbumTypeParsingTest(NameTestCaseBase):
    def test_album_with_repackage_1(self):
        page = page_with_info("""
        ''Perfect Velvet'' is the second full-length album released by [[Red Velvet]]. The song "[[Peek-A-Boo]]" was used as the lead track
        
        A repackage album was released two months later, titled ''The Perfect Red Velvet''. The song "[[Bad Boy (Red Velvet)|Bad Boy]]" was used as the lead track.
        """)
        num = parse_generasia_album_number(page)
        self.assertEqual(num, 2)

    def test_mini_album(self):
        page = page_with_info("""
        ''Red Moon'' is the seventh mini-album released by [[MAMAMOO]]. The song "[[Neona Hae]]" was used as the lead track.
        """)
        num = parse_generasia_album_number(page)
        self.assertEqual(num, 7)

    def test_collab_digital_single(self):
        page = page_with_info("""
        "Haengbok Hajima" is a collaboration digital single between [[MAMAMOO]] and [[Bumkey]].
        """)
        num = parse_generasia_album_number(page)
        self.assertIs(num, None)

    def test_album_with_repackage_2(self):
        page = page_with_info("""
        ''Oh!'' is [[Girls' Generation]]'s second album. The title track, "[[Oh! (song)|Oh!]]", was used as lead single, and the second track "[[Show! Show! Show!]]" was used as the second single. The album was later re-released as a repackage album titled ''Run Devil Run'' with 2 new songs and an acoustic version included. "[[Run Devil Run (single)|Run Devil Run]]", the title track, was used as the lead single. The re-package album featured only one [[Girls' Generation]] member on the cover, [[Yoona]], and the album came with 1 random poster (1 of 9) featuring a different member on each one.
        """)
        num = parse_generasia_album_number(page)
        self.assertEqual(num, 2)

    def test_album_with_repackage_3(self):
        page = page_with_info("""
        ''The Boys'' is [[Girls' Generation]]'s third album. The title track was used as lead single. Two months later, the album was re-released as a repackage album. The re-packaged album features the same tracklist as ''The Boys'', however the title/lead track "[[Mr. Taxi|MR. TAXI]]" was moved to the top and the album includes the English version of "[[The Boys (Girls' Generation single)|The Boys]]", previously released as their first USA single and on the digital edition of ''The Boys''. In January and February of 2012, the album was released in USA and Europe respectively. Instead of the original tracklist both the Korean and English versions were swapped around and 4 remixes of "[[The Boys (Girls' Generation single)|The Boys]]" were included.
        """)
        num = parse_generasia_album_number(page)
        self.assertEqual(num, 3)

    def test_album_with_repackage_4(self):
        page = page_with_info("""
        ''XOXO'' is [[EXO]]'s first album. The album was released in two versions; the Kiss Edition, which contains the Korean version of the songs and the Hug Edition, which contains the Chinese version of the songs. "[[Wolf (EXO)|Neukdaewa Minyeo (Wolf)]]" was used as the lead track. Other than the lead track which is sung by the whole of EXO, the Kiss Edition of the songs are sung by EXO-K while the Hug Edition of the songs are sung by EXO-M. The Kiss Edition reached #9, charted for 59 weeks and sold 76,592 copies according to [[Oricon]] Album Charts, the Hug Edition charted for 32 weeks and sold 29,082 copies according to [[Oricon]] Album Charts.

        Two months later a repackage of the album was released. "[[Growl (EXO)|Eureureong (Growl)]]" was used as the lead track.
        """)
        num = parse_generasia_album_number(page)
        self.assertEqual(num, 1)

    def test_album_1(self):
        page = page_with_info("""
        ''Love Yourself Gyeol 'Answer''' is the fifth full-length album released by [[Bangtan Boys]], and the final part of the "Love Yourself" trilogy. The song "[[Idol (BTS)|IDOL]]" was used as the lead track.

        Despite being a Korean release, the album ranked #1 on the [[Oricon]] weekly albums chart and is certified [http://www.riaj.or.jp/f/data/cert/gd.html Gold] by [[RIAJ]] for shipment of 100,000 copies.
        """)
        num = parse_generasia_album_number(page)
        self.assertEqual(num, 5)


if __name__ == '__main__':
    main(GenerasiaAlbumTypeParsingTest)
