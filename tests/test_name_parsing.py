#!/usr/bin/env python

import logging
import sys
import unittest
from pathlib import Path

sys.path.append(Path(__file__).parents[1].joinpath('lib').as_posix())
from ds_tools.logging import init_logging
from wiki_nodes.nodes import as_node
from music_manager.wiki.utils import parse_generasia_name

log = logging.getLogger(__name__)


class NameParsingTest(unittest.TestCase):
    def test_rom_han_lit(self):
        entry = as_node('''[2007.11.01] [[So Nyeo Si Dae]] (소녀시대; ''Girls' Generation'')''')
        name = parse_generasia_name(entry)
        self.assertEqual(name.romanized, 'So Nyeo Si Dae')
        self.assertEqual(name.non_eng, '소녀시대')
        self.assertEqual(name.lit_translation, 'Girls\' Generation')
        self.assertEqual(name.korean, '소녀시대')
        self.assertEqual(name.english, name.lit_translation)

    # def test_eng_repackage(self):
    #     entry = as_node('''[2008.03.17] [[So Nyeo Si Dae|Baby Baby]] ''(Repackage Album)''''')
    #     name = parse_generasia_name(entry)
    #
    # def test_eng_simple(self):
    #     entry = as_node('''[2010.01.28] [[Oh!]]''')
    #     name = parse_generasia_name(entry)
    #
    # def test_rom_eng_han_lit(self):
    #     entry = as_node('''[2009.06.29] [[Sowoneul Malhaebwa (Genie)]] (소원을 말해봐; ''Tell Me Your Wish'')''')
    #     name = parse_generasia_name(entry)
    #
    # def test_eng_alb_type(self):
    #     entry = as_node('''[2008.02.18] [[Sweet Memories With Girls' Generation|Sweet Memories with Girls' Generation]] ''(Song Selection Album)''''')
    #     name = parse_generasia_name(entry)
    #
    # def test_rom_eng_han(self):
    #     entry = as_node('''[2007.08.02] [[Dasi Mannan Segye (Into the New World)|Dasi Mannan Segye (Into the new world)]] (다시 만난 세계)''')
    #     name = parse_generasia_name(entry)
    #
    # def test_rom_eng_remix_han(self):
    #     entry = as_node('''[2007.09.13] [[Dasi Mannan Segye (Into the New World)|Dasi Mannan Segye (Into the new world) Remix]] (다시 만난 세계)''')
    #     name = parse_generasia_name(entry)
    #
    # def test_eng_parens(self):
    #     # "POP!POP!" should be part of the english name here...
    #     entry = as_node('''[2011.01.17] [[Visual Dreams (Pop!Pop!)|Visual Dreams (POP!POP!)]]''')
    #     name = parse_generasia_name(entry)
    #
    # def test_song_paren_ost(self):
    #     entry = as_node('''[2013.12.01] [[Find Your Soul (Blade & Soul 2013 OST)]]''')
    #     name = parse_generasia_name(entry)
    #
    # def test_rom_han(self):
    #     entry = as_node('''[2016.08.05] [[Geu Yeoleum]] (그 여름)''')
    #     name = parse_generasia_name(entry)
    #
    # def test_ost_multiple_songs(self):
    #     entry = as_node('''[2007.11.23] [[Thirty Thousand Miles in Search of My Son OST]] ''(#1 Touch the Sky (Original Ver.), #13 Touch the Sky (Drama Ver.))''''')
    #     name = parse_generasia_name(entry)
    #
    # def test_eng_album_plus_track(self):
    #     entry = as_node('''[2007.12.07] [[2007 Winter SMTown|2007 WINTER SMTOWN]] ''(#7 Lovely Melody)''''')
    #     name = parse_generasia_name(entry)
    #
    # def test_eng_album_track_various_artists(self):
    #     entry = as_node('''[2007.12.13] [[Light]] ''(#1 Light (Various Artists))''''')
    #     name = parse_generasia_name(entry)
    #
    # def test_eng_ost_track(self):
    #     entry = as_node('''[2008.01.22] [[Hong Gil Dong OST]] ''(#5 Jak Eun Bae)''''')
    #     name = parse_generasia_name(entry)
    #
    # def test_eng_rom_artists(self):
    #     entry = as_node('''[2008.05.08] [[Haptic Motion]] (햅틱모션) <small>([[Jessica]], [[Yoona]], [[Tiffany]], [[Tong Vfang Xien Qi|Dong Bang Shin Ki]])</small>''')
    #     name = parse_generasia_name(entry)
    #
    # def test_primary_dash_eng_paren_track_paren_collabs(self):
    #     entry = as_node("""[2008.12.05] [[Yoon Sang]] - [[Song Book Play With Him|Song Book: Play With Him]] ''(#3 Lallalla ('''Girls' Generation''' + Yoon Sang))''""")
    #     name = parse_generasia_name(entry)
    #
    # def test_eng_with_parens_artists(self):
    #     entry = as_node('''[2009.12.15] [[Seoul (Seoul City Promotional Song)|SEOUL (Seoul City Promotional Song) ]] <small>([[Taeyeon]], [[Jessica]], [[Sunny]], [[Seohyun]], [[Kyuhyun]], [[Ryeowook]], [[Sungmin]], [[Donghae]])</small>''')
    #     name = parse_generasia_name(entry)
    #
    # def test_artists_dash_album(self):
    #     entry = as_node("""[2010.05.20] [[2PM]] & '''Girls' Generation''' - [[Cabi Song]]""")
    #     name = parse_generasia_name(entry)
    #
    # def test_project_track_slash_collabs(self):
    #     entry = as_node("""[2013.03.28] [[10 Corso Como Seoul Melody Collaboration Project|10 CORSO COMO SEOUL MELODY Collaboration Project]] (#1 ''Trick'' / '''Girls Generation''' x DJ Soul Scape'')""")
    #     name = parse_generasia_name(entry)
    #
    # def test_eng_ost_han_no_ost(self):
    #     entry = as_node('''[2015.09.16] [[Innisia Nest OST]] (이니시아 네스트)''')
    #     name = parse_generasia_name(entry)
    #
    # def test_mixed_rom_han_lit(self):
    #     entry = as_node('''[2016.02.12] [[1cm Ui Jajonsim]] (1cm의 자존심; ''1cm Pride'')''')
    #     name = parse_generasia_name(entry)
    #
    # def test_ost_part_rom_han_lit(self):
    #     entry = as_node('''[2017.03.24] [[Himssenyeoja Dobongsun OST Part 5]] (힘쎈여자 도봉순 OST Part 5; ''A Strong Woman OST Part 5'')''')
    #     name = parse_generasia_name(entry)
    #
    # def test_ost_part_eng_han(self):
    #     entry = as_node('''[2017.05.09] [[Man to Man OST Part 5]] (맨투맨 OST Part 5)''')
    #     name = parse_generasia_name(entry)
    #
    # def test_ost_part_eng(self):
    #     entry = as_node('''[2018.05.09] [[Suits OST Part 3]]''')
    #     name = parse_generasia_name(entry)
    #
    # def test_rom_han_eng(self):
    #     entry = as_node('''[2018.07.01] [[Jangma]] (장마; ''Rainy Season'')''')
    #     name = parse_generasia_name(entry)
    #
    # def test_ost_part_rom_incomplete_han_lit(self):
    #     entry = as_node('''[2020.01.28] [[Nangmandagteo Kimsabu 2 OST Part 6]] (낭만닥터 김사부; ''Romantic Doctor'')''')
    #     name = parse_generasia_name(entry)
    #
    # def test_rom_han_eng_collabs(self):
    #     entry = as_node("""[2014.01.09] [[Haengbok Hajima]] (행복하지마; ''Don't Be Happy'') <small>('''mamamoo''' & [[Bumkey]])</small>""")
    #     name = parse_generasia_name(entry)
    #
    # def test_rom_han_eng_collabs_feat(self):
    #     entry = as_node("""[2014.02.11] [[Sseomnam Sseomnyeo]] (썸남썸녀; ''Peppermint Chocolate'') <small>([[K.Will]] & '''mamamoo''' ft. [[Wheesung]])</small>""")
    #     name = parse_generasia_name(entry)
    #
    # def test_eng_han_collabs(self):
    #     entry = as_node("""[2014.05.30] [[Hi Hi Ha He Ho]] (히히하헤호) <small>('''MAMAMOO''' & [[Geeks]])</small>""")
    #     name = parse_generasia_name(entry)
    #
    # def test_eng_collabs(self):
    #     entry = as_node("""[2015.04.02] [[Ahh Oop!|AHH OOP!]] <small>('''MAMAMOO''' & [[eSNa]])</small>""")
    #     name = parse_generasia_name(entry)
    #
    # def test_ost_part_rom_incomplete_han_collabs(self):
    #     entry = as_node("""[2015.10.31] [[Naegen Neomu Sarangseureoun Geunyeo OST Part 1]] (내겐 너무 사랑스러운 그녀) <small>([[LOCO]] & '''MAMAMOO''', [[Park Mi Young]])</small>""")
    #     name = parse_generasia_name(entry)
    #
    # def test_ost_rom_track(self):
    #     entry = as_node('''[2014.08.29] [[Yeonaemalgo Gyeolhon OST]] (#2 ''Love Lane'')''')
    #     name = parse_generasia_name(entry)
    #
    # def test_ost_rom_track_missing_num(self):
    #     entry = as_node('''[2014.11.06] [[Naegen Neomu Sarangseureoun Geunyeo OST]] (# ''I Norae'')''')
    #     name = parse_generasia_name(entry)
    #
    # def test_ost_eng_track_rom_eng(self):
    #     entry = as_node('''[2015.03.12] [[Spy OST]] (#6 ''Nae Nun Sogen Neo (My Everything)'')''')
    #     name = parse_generasia_name(entry)
    #
    # def test_competition_part_track(self):
    #     entry = as_node('''[2019.09.13] [[Queendom (Covergog Gyeongyeon) Part 1|Queendom [Covergog Gyeongyeon] Part 1]] (#1 ''Good Luck'')''')
    #     name = parse_generasia_name(entry)
    #
    # def test_competition_part_track_missing_num(self):
    #     entry = as_node('''[2019.10.18] [[Queendom (Pandoraui Sangja) Part 1|Queendom [Pandoraui Sangja] Part 1]] (# ''I Miss You'')''')
    #     name = parse_generasia_name(entry)
    #
    # def test_competition_track_rom_eng(self):
    #     entry = as_node('''[2019.10.25] [[Queendom (Final Comeback Single)|Queendom [FINAL Comeback Single]]] (#6 ''Urin Gyeolgug Dasi Mannal Unmyeongieossji (Destiny)'')''')
    #     name = parse_generasia_name(entry)
    #
    # def test_rom_han_eng_feat(self):
    #     entry = as_node('''[2012.01.20] [[Michinyeonae]] (미친연애; ''Bad Girl'') (feat. [[E-Sens]] of [[Supreme Team]])''')
    #     name = parse_generasia_name(entry)
    #
    # def test_eng_x_collabs(self):
    #     entry = as_node("""[2019.01.10] [[Carpet]] <small>([[Yesung]] x '''Bumkey''')</small>""")
    #     name = parse_generasia_name(entry)

    # def test_(self):
    #     entry = as_node('''''')
    #     name = parse_generasia_name(entry)


if __name__ == '__main__':
    init_logging(0, log_path=None)
    try:
        unittest.main(warnings='ignore', verbosity=2, exit=False)
    except KeyboardInterrupt:
        print()
