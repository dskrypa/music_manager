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
    # def setUp(self):
    #     print()

    def test_rom_han_lit(self):
        entry = as_node('''[2007.11.01] [[So Nyeo Si Dae]] (소녀시대; ''Girls' Generation'')''')
        name = parse_generasia_name(entry)
        self.assertEqual(name.romanized, 'So Nyeo Si Dae')
        self.assertEqual(name.non_eng, '소녀시대')
        self.assertEqual(name.lit_translation, 'Girls\' Generation')
        self.assertEqual(name.korean, '소녀시대')
        self.assertIs(name.japanese, None)
        self.assertIs(name.cjk, None)
        self.assertEqual(name.english, name.lit_translation)

    def test_eng_repackage(self):
        entry = as_node('''[2008.03.17] [[So Nyeo Si Dae|Baby Baby]] ''(Repackage Album)''''')
        name = parse_generasia_name(entry)
        self.assertEqual(name.english, 'Baby Baby')
        self.assertEqual(name._english, 'Baby Baby')
        self.assertEqual(name.extra, 'Repackage Album')
        self.assertIs(name.non_eng, None)
        self.assertIs(name.romanized, None)
        self.assertIs(name.lit_translation, None)

    def test_eng_simple(self):
        entry = as_node('''[2010.01.28] [[Oh!]]''')
        name = parse_generasia_name(entry)
        self.assertEqual(name.english, 'Oh!')
        self.assertEqual(name._english, 'Oh!')
        self.assertIs(name.non_eng, None)
        self.assertIs(name.romanized, None)
        self.assertIs(name.lit_translation, None)

    def test_rom_eng_han_lit(self):
        entry = as_node('''[2009.06.29] [[Sowoneul Malhaebwa (Genie)]] (소원을 말해봐; ''Tell Me Your Wish'')''')
        name = parse_generasia_name(entry)
        self.assertEqual(name.english, 'Genie')
        self.assertEqual(name._english, 'Genie')
        self.assertEqual(name.non_eng, '소원을 말해봐')
        self.assertEqual(name.korean, '소원을 말해봐')
        self.assertIs(name.japanese, None)
        self.assertIs(name.cjk, None)
        self.assertEqual(name.romanized, 'Sowoneul Malhaebwa')
        self.assertEqual(name.lit_translation, 'Tell Me Your Wish')

    def test_eng_alb_type(self):
        entry = as_node('''[2008.02.18] [[Sweet Memories With Girls' Generation|Sweet Memories with Girls' Generation]] ''(Song Selection Album)''''')
        name = parse_generasia_name(entry)
        self.assertEqual(name.english, 'Sweet Memories with Girls\' Generation')
        self.assertEqual(name._english, 'Sweet Memories with Girls\' Generation')
        self.assertIs(name.non_eng, None)
        self.assertIs(name.romanized, None)
        self.assertIs(name.lit_translation, None)
        self.assertEqual(name.extra, 'Song Selection Album')

    def test_rom_eng_han(self):
        entry = as_node('''[2007.08.02] [[Dasi Mannan Segye (Into the New World)|Dasi Mannan Segye (Into the new world)]] (다시 만난 세계)''')
        name = parse_generasia_name(entry)
        self.assertEqual(name.english, 'Into the new world')
        self.assertEqual(name._english, 'Into the new world')
        self.assertEqual(name.non_eng, '다시 만난 세계')
        self.assertEqual(name.korean, '다시 만난 세계')
        self.assertIs(name.japanese, None)
        self.assertIs(name.cjk, None)
        self.assertEqual(name.romanized, 'Dasi Mannan Segye')
        self.assertIs(name.lit_translation, None)

    def test_rom_eng_remix_han(self):
        entry = as_node('''[2007.09.13] [[Dasi Mannan Segye (Into the New World)|Dasi Mannan Segye (Into the new world) Remix]] (다시 만난 세계)''')
        name = parse_generasia_name(entry)
        self.assertEqual(name.english, 'Into the new world')
        self.assertEqual(name._english, 'Into the new world')
        self.assertEqual(name.non_eng, '다시 만난 세계')
        self.assertEqual(name.korean, '다시 만난 세계')
        self.assertIs(name.japanese, None)
        self.assertIs(name.cjk, None)
        self.assertEqual(name.romanized, 'Dasi Mannan Segye')
        self.assertIs(name.lit_translation, None)
        self.assertEqual(name.extra, 'Remix')

    def test_eng_parens(self):
        # "POP!POP!" should be part of the english name here...
        entry = as_node('''[2011.01.17] [[Visual Dreams (Pop!Pop!)|Visual Dreams (POP!POP!)]]''')
        name = parse_generasia_name(entry)
        self.assertEqual(name.english, 'Visual Dreams (POP!POP!)')
        self.assertEqual(name._english, 'Visual Dreams (POP!POP!)')
        self.assertIs(name.non_eng, None)
        self.assertIs(name.korean, None)
        self.assertIs(name.japanese, None)
        self.assertIs(name.cjk, None)
        self.assertIs(name.romanized, None)
        self.assertIs(name.lit_translation, None)
        self.assertIs(name.extra, None)

    def test_rom_han(self):
        entry = as_node('''[2016.08.05] [[Geu Yeoleum]] (그 여름)''')
        name = parse_generasia_name(entry)
        self.assertIs(name.english, None)
        self.assertIs(name._english, None)
        self.assertEqual(name.non_eng, '그 여름')
        self.assertEqual(name.korean, '그 여름')
        self.assertIs(name.japanese, None)
        self.assertIs(name.cjk, None)
        self.assertEqual(name.romanized, 'Geu Yeoleum')
        self.assertIs(name.lit_translation, None)

    def test_ost_multiple_songs(self):
        entry = as_node('''[2007.11.23] [[Thirty Thousand Miles in Search of My Son OST]] ''(#1 Touch the Sky (Original Ver.), #13 Touch the Sky (Drama Ver.))''''')
        name = parse_generasia_name(entry)
        self.assertEqual(name.english, 'Thirty Thousand Miles in Search of My Son OST')
        self.assertEqual(name._english, 'Thirty Thousand Miles in Search of My Son OST')
        self.assertIs(name.non_eng, None)
        self.assertIs(name.korean, None)
        self.assertIs(name.japanese, None)
        self.assertIs(name.cjk, None)
        self.assertIs(name.romanized, None)
        self.assertIs(name.lit_translation, None)
        self.assertEqual(name.extra, '#1 Touch the Sky (Original Ver.), #13 Touch the Sky (Drama Ver.)')

    def test_eng_album_plus_track(self):
        entry = as_node('''[2007.12.07] [[2007 Winter SMTown|2007 WINTER SMTOWN]] ''(#7 Lovely Melody)''''')
        name = parse_generasia_name(entry)
        self.assertEqual(name.english, '2007 WINTER SMTOWN')
        self.assertEqual(name._english, '2007 WINTER SMTOWN')
        self.assertIs(name.non_eng, None)
        self.assertIs(name.korean, None)
        self.assertIs(name.japanese, None)
        self.assertIs(name.cjk, None)
        self.assertIs(name.romanized, None)
        self.assertIs(name.lit_translation, None)
        self.assertEqual(name.extra, '#7 Lovely Melody')

    def test_eng_album_track_various_artists(self):
        entry = as_node('''[2007.12.13] [[Light]] ''(#1 Light (Various Artists))''''')
        name = parse_generasia_name(entry)
        self.assertEqual(name.english, 'Light')
        self.assertEqual(name._english, 'Light')
        self.assertIs(name.non_eng, None)
        self.assertIs(name.korean, None)
        self.assertIs(name.japanese, None)
        self.assertIs(name.cjk, None)
        self.assertIs(name.romanized, None)
        self.assertIs(name.lit_translation, None)
        self.assertEqual(name.extra, '#1 Light (Various Artists)')

    def test_eng_ost_track(self):
        entry = as_node('''[2008.01.22] [[Hong Gil Dong OST]] ''(#5 Jak Eun Bae)''''')
        name = parse_generasia_name(entry)
        self.assertEqual(name.english, 'Hong Gil Dong OST')
        self.assertEqual(name._english, 'Hong Gil Dong OST')
        self.assertEqual(name.non_eng, None)
        self.assertEqual(name.korean, None)
        self.assertIs(name.japanese, None)
        self.assertIs(name.cjk, None)
        self.assertEqual(name.romanized, None)
        self.assertEqual(name.lit_translation, None)
        self.assertEqual(name.extra, '#5 Jak Eun Bae')

    def test_eng_rom_artists(self):
        entry = as_node('''[2008.05.08] [[Haptic Motion]] (햅틱모션) <small>([[Jessica]], [[Yoona]], [[Tiffany]], [[Tong Vfang Xien Qi|Dong Bang Shin Ki]])</small>''')
        name = parse_generasia_name(entry)
        self.assertEqual(name.english, 'Haptic Motion')
        self.assertEqual(name._english, 'Haptic Motion')
        self.assertEqual(name.non_eng, '햅틱모션')
        self.assertEqual(name.korean, '햅틱모션')
        self.assertIs(name.japanese, None)
        self.assertIs(name.cjk, None)
        self.assertEqual(name.romanized, None)
        self.assertEqual(name.lit_translation, None)
        self.assertIs(name.extra, None)

    def test_primary_dash_eng_paren_track_paren_collabs(self):
        entry = as_node("""[2008.12.05] [[Yoon Sang]] - [[Song Book Play With Him|Song Book: Play With Him]] ''(#3 Lallalla ('''Girls' Generation''' + Yoon Sang))''""")
        name = parse_generasia_name(entry)
        self.assertEqual(name.english, 'Song Book: Play With Him')
        self.assertEqual(name._english, 'Song Book: Play With Him')
        self.assertIs(name.non_eng, None)
        self.assertIs(name.korean, None)
        self.assertIs(name.japanese, None)
        self.assertIs(name.cjk, None)
        self.assertIs(name.romanized, None)
        self.assertIs(name.lit_translation, None)
        self.assertEqual(name.extra, '#3 Lallalla (Girls\' Generation + Yoon Sang)')

    def test_eng_with_parens_artists(self):
        entry = as_node('''[2009.12.15] [[Seoul (Seoul City Promotional Song)|SEOUL (Seoul City Promotional Song) ]] <small>([[Taeyeon]], [[Jessica]], [[Sunny]], [[Seohyun]], [[Kyuhyun]], [[Ryeowook]], [[Sungmin]], [[Donghae]])</small>''')
        name = parse_generasia_name(entry)
        self.assertEqual(name.english, 'SEOUL (Seoul City Promotional Song)')
        self.assertEqual(name._english, 'SEOUL (Seoul City Promotional Song)')
        self.assertIs(name.non_eng, None)
        self.assertIs(name.korean, None)
        self.assertIs(name.japanese, None)
        self.assertIs(name.cjk, None)
        self.assertIs(name.romanized, None)
        self.assertIs(name.lit_translation, None)
        self.assertIs(name.extra, None)

    def test_project_track_slash_collabs(self):
        # Note: the extras on this line have an extra trailing ''
        entry = as_node("""[2013.03.28] [[10 Corso Como Seoul Melody Collaboration Project|10 CORSO COMO SEOUL MELODY Collaboration Project]] (#1 ''Trick'' / '''Girls Generation''' x DJ Soul Scape'')""")
        name = parse_generasia_name(entry)
        self.assertEqual(name.english, '10 CORSO COMO SEOUL MELODY Collaboration Project')
        self.assertEqual(name._english, '10 CORSO COMO SEOUL MELODY Collaboration Project')
        self.assertIs(name.non_eng, None)
        self.assertIs(name.korean, None)
        self.assertIs(name.japanese, None)
        self.assertIs(name.cjk, None)
        self.assertIs(name.romanized, None)
        self.assertIs(name.lit_translation, None)
        self.assertEqual(name.extra, '#1 Trick / Girls Generation x DJ Soul Scape')

    def test_eng_ost_han_no_ost(self):
        entry = as_node('''[2015.09.16] [[Innisia Nest OST]] (이니시아 네스트)''')
        name = parse_generasia_name(entry)
        self.assertEqual(name.english, 'Innisia Nest OST')
        self.assertEqual(name._english, 'Innisia Nest OST')
        self.assertEqual(name.non_eng, '이니시아 네스트')
        self.assertEqual(name.korean, '이니시아 네스트')
        self.assertIs(name.japanese, None)
        self.assertIs(name.cjk, None)
        self.assertIs(name.romanized, None)
        self.assertIs(name.lit_translation, None)
        self.assertIs(name.extra, None)

    def test_mixed_rom_han_lit(self):
        entry = as_node('''[2016.02.12] [[1cm Ui Jajonsim]] (1cm의 자존심; ''1cm Pride'')''')
        name = parse_generasia_name(entry)
        self.assertEqual(name.english, '1cm Pride')
        self.assertIs(name._english, None)
        self.assertEqual(name.non_eng, '1cm의 자존심')
        self.assertEqual(name.korean, '1cm의 자존심')
        self.assertIs(name.japanese, None)
        self.assertIs(name.cjk, None)
        self.assertEqual(name.romanized, '1cm Ui Jajonsim')
        self.assertEqual(name.lit_translation, '1cm Pride')
        self.assertIs(name.extra, None)

    def test_ost_part_rom_han_lit(self):
        entry = as_node('''[2017.03.24] [[Himssenyeoja Dobongsun OST Part 5]] (힘쎈여자 도봉순 OST Part 5; ''A Strong Woman OST Part 5'')''')
        name = parse_generasia_name(entry)
        self.assertEqual(name.english, name.lit_translation)
        self.assertIs(name._english, None)
        self.assertEqual(name.non_eng, '힘쎈여자 도봉순 OST Part 5')
        self.assertEqual(name.korean, '힘쎈여자 도봉순 OST Part 5')
        self.assertIs(name.japanese, None)
        self.assertIs(name.cjk, None)
        self.assertEqual(name.romanized, 'Himssenyeoja Dobongsun OST Part 5')
        self.assertEqual(name.lit_translation, 'A Strong Woman OST Part 5')
        self.assertIs(name.extra, None)

    def test_ost_part_eng_han(self):
        entry = as_node('''[2017.05.09] [[Man to Man OST Part 5]] (맨투맨 OST Part 5)''')
        name = parse_generasia_name(entry)
        self.assertEqual(name.english, 'Man to Man OST Part 5')
        self.assertEqual(name._english, 'Man to Man OST Part 5')
        self.assertEqual(name.non_eng, '맨투맨 OST Part 5')
        self.assertEqual(name.korean, '맨투맨 OST Part 5')
        self.assertIs(name.japanese, None)
        self.assertIs(name.cjk, None)
        self.assertIs(name.romanized, None)
        self.assertIs(name.lit_translation, None)
        self.assertIs(name.extra, None)

    def test_ost_part_eng(self):
        entry = as_node('''[2018.05.09] [[Suits OST Part 3]]''')
        name = parse_generasia_name(entry)
        self.assertEqual(name.english, 'Suits OST Part 3')
        self.assertEqual(name._english, 'Suits OST Part 3')
        self.assertIs(name.non_eng, None)
        self.assertIs(name.korean, None)
        self.assertIs(name.japanese, None)
        self.assertIs(name.cjk, None)
        self.assertIs(name.romanized, None)
        self.assertIs(name.lit_translation, None)
        self.assertIs(name.extra, None)

    def test_rom_han_eng(self):
        entry = as_node('''[2018.07.01] [[Jangma]] (장마; ''Rainy Season'')''')
        name = parse_generasia_name(entry)
        self.assertEqual(name.english, 'Rainy Season')
        self.assertIs(name._english, None)
        self.assertEqual(name.non_eng, '장마')
        self.assertEqual(name.korean, '장마')
        self.assertIs(name.japanese, None)
        self.assertIs(name.cjk, None)
        self.assertEqual(name.romanized, 'Jangma')
        self.assertEqual(name.lit_translation, 'Rainy Season')
        self.assertIs(name.extra, None)

    def test_rom_han_eng_collabs(self):
        entry = as_node("""[2014.01.09] [[Haengbok Hajima]] (행복하지마; ''Don't Be Happy'') <small>('''mamamoo''' & [[Bumkey]])</small>""")
        name = parse_generasia_name(entry)
        self.assertEqual(name.english, 'Don\'t Be Happy')
        self.assertIs(name._english, None)
        self.assertEqual(name.non_eng, '행복하지마')
        self.assertEqual(name.korean, '행복하지마')
        self.assertIs(name.japanese, None)
        self.assertIs(name.cjk, None)
        self.assertEqual(name.romanized, 'Haengbok Hajima')
        self.assertEqual(name.lit_translation, 'Don\'t Be Happy')
        self.assertIs(name.extra, None)

    def test_rom_han_eng_collabs_feat(self):
        entry = as_node("""[2014.02.11] [[Sseomnam Sseomnyeo]] (썸남썸녀; ''Peppermint Chocolate'') <small>([[K.Will]] & '''mamamoo''' ft. [[Wheesung]])</small>""")
        name = parse_generasia_name(entry)
        self.assertEqual(name.english, 'Peppermint Chocolate')
        self.assertIs(name._english, None)
        self.assertEqual(name.non_eng, '썸남썸녀')
        self.assertEqual(name.korean, '썸남썸녀')
        self.assertIs(name.japanese, None)
        self.assertIs(name.cjk, None)
        self.assertEqual(name.romanized, 'Sseomnam Sseomnyeo')
        self.assertEqual(name.lit_translation, 'Peppermint Chocolate')
        self.assertIs(name.extra, None)

    def test_eng_han_collabs(self):
        entry = as_node("""[2014.05.30] [[Hi Hi Ha He Ho]] (히히하헤호) <small>('''MAMAMOO''' & [[Geeks]])</small>""")
        name = parse_generasia_name(entry)
        self.assertEqual(name.english, 'Hi Hi Ha He Ho')
        self.assertEqual(name._english, 'Hi Hi Ha He Ho')   # because it's in the title position
        self.assertEqual(name.non_eng, '히히하헤호')
        self.assertEqual(name.korean, '히히하헤호')
        self.assertIs(name.japanese, None)
        self.assertIs(name.cjk, None)
        self.assertIs(name.romanized, None)
        self.assertIs(name.lit_translation, None)
        self.assertIs(name.extra, None)

    def test_eng_collabs(self):
        entry = as_node("""[2015.04.02] [[Ahh Oop!|AHH OOP!]] <small>('''MAMAMOO''' & [[eSNa]])</small>""")
        name = parse_generasia_name(entry)
        self.assertEqual(name.english, 'AHH OOP!')
        self.assertEqual(name._english, 'AHH OOP!')
        self.assertEqual(name.non_eng, None)
        self.assertEqual(name.korean, None)
        self.assertIs(name.japanese, None)
        self.assertIs(name.cjk, None)
        self.assertIs(name.romanized, None)
        self.assertIs(name.lit_translation, None)
        self.assertIs(name.extra, None)

    def test_ost_rom_track(self):
        # Would prefer that this be captured as a romanization, but that would be tough
        entry = as_node('''[2014.08.29] [[Yeonaemalgo Gyeolhon OST]] (#2 ''Love Lane'')''')
        name = parse_generasia_name(entry)
        self.assertEqual(name.english, 'Yeonaemalgo Gyeolhon OST')
        self.assertEqual(name._english, 'Yeonaemalgo Gyeolhon OST')
        self.assertIs(name.non_eng, None)
        self.assertIs(name.korean, None)
        self.assertIs(name.japanese, None)
        self.assertIs(name.cjk, None)
        self.assertIs(name.romanized, None)
        self.assertIs(name.lit_translation, None)
        self.assertEqual(name.extra, '#2 Love Lane')

    def test_ost_rom_track_missing_num(self):
        # Would prefer that this be captured as a romanization, but that would be tough
        # This is really better suited to be tested as a full line parse test, rather than just the name
        entry = as_node('''[2014.11.06] [[Naegen Neomu Sarangseureoun Geunyeo OST]] (# ''I Norae'')''')
        name = parse_generasia_name(entry)
        self.assertEqual(name.english, 'Naegen Neomu Sarangseureoun Geunyeo OST')
        self.assertEqual(name._english, 'Naegen Neomu Sarangseureoun Geunyeo OST')
        self.assertIs(name.non_eng, None)
        self.assertIs(name.korean, None)
        self.assertIs(name.japanese, None)
        self.assertIs(name.cjk, None)
        self.assertIs(name.romanized, None)
        self.assertIs(name.lit_translation, None)
        self.assertEqual(name.extra, '# I Norae')

    def test_ost_eng_track_rom_eng(self):
        entry = as_node('''[2015.03.12] [[Spy OST]] (#6 ''Nae Nun Sogen Neo (My Everything)'')''')
        name = parse_generasia_name(entry)
        self.assertEqual(name.english, 'Spy OST')
        self.assertEqual(name._english, 'Spy OST')
        self.assertIs(name.non_eng, None)
        self.assertIs(name.korean, None)
        self.assertIs(name.japanese, None)
        self.assertIs(name.cjk, None)
        self.assertIs(name.romanized, None)
        self.assertIs(name.lit_translation, None)
        self.assertEqual(name.extra, '#6 Nae Nun Sogen Neo (My Everything)')

    def test_competition_part_track(self):
        entry = as_node('''[2019.09.13] [[Queendom (Covergog Gyeongyeon) Part 1|Queendom [Covergog Gyeongyeon] Part 1]] (#1 ''Good Luck'')''')
        name = parse_generasia_name(entry)
        self.assertEqual(name.english, 'Queendom [Covergog Gyeongyeon] Part 1')
        self.assertEqual(name._english, 'Queendom [Covergog Gyeongyeon] Part 1')
        self.assertIs(name.non_eng, None)
        self.assertIs(name.korean, None)
        self.assertIs(name.japanese, None)
        self.assertIs(name.cjk, None)
        self.assertIs(name.romanized, None)
        self.assertIs(name.lit_translation, None)
        self.assertEqual(name.extra, '#1 Good Luck')

    def test_competition_part_track_missing_num(self):
        entry = as_node('''[2019.10.18] [[Queendom (Pandoraui Sangja) Part 1|Queendom [Pandoraui Sangja] Part 1]] (# ''I Miss You'')''')
        name = parse_generasia_name(entry)
        self.assertEqual(name.english, 'Queendom [Pandoraui Sangja] Part 1')
        self.assertEqual(name._english, 'Queendom [Pandoraui Sangja] Part 1')
        self.assertIs(name.non_eng, None)
        self.assertIs(name.korean, None)
        self.assertIs(name.japanese, None)
        self.assertIs(name.cjk, None)
        self.assertIs(name.romanized, None)
        self.assertIs(name.lit_translation, None)
        self.assertEqual(name.extra, '# I Miss You')

    def test_competition_track_rom_eng(self):
        entry = as_node('''[2019.10.25] [[Queendom (Final Comeback Single)|Queendom [FINAL Comeback Single]]] (#6 ''Urin Gyeolgug Dasi Mannal Unmyeongieossji (Destiny)'')''')
        name = parse_generasia_name(entry)
        # self.assertEqual(name.english, 'Queendom [FINAL Comeback Single]')
        # self.assertEqual(name._english, 'Queendom [FINAL Comeback Single]')
        self.assertEqual(name.english, 'Queendom [FINAL Comeback Single')       # TODO: update after link bug is fixed
        self.assertEqual(name._english, 'Queendom [FINAL Comeback Single')      # in upstream lib
        self.assertIs(name.non_eng, None)
        self.assertIs(name.korean, None)
        self.assertIs(name.japanese, None)
        self.assertIs(name.cjk, None)
        self.assertIs(name.romanized, None)
        self.assertIs(name.lit_translation, None)
        self.assertEqual(name.extra, '#6 Urin Gyeolgug Dasi Mannal Unmyeongieossji (Destiny)')

    def test_rom_han_eng_feat(self):
        entry = as_node('''[2012.01.20] [[Michinyeonae]] (미친연애; ''Bad Girl'') (feat. [[E-Sens]] of [[Supreme Team]])''')
        name = parse_generasia_name(entry)
        self.assertEqual(name.english, 'Bad Girl')
        self.assertIs(name._english, None)
        self.assertEqual(name.non_eng, '미친연애')
        self.assertEqual(name.korean, '미친연애')
        self.assertIs(name.japanese, None)
        self.assertIs(name.cjk, None)
        self.assertEqual(name.romanized, 'Michinyeonae')
        self.assertEqual(name.lit_translation, 'Bad Girl')
        self.assertIs(name.extra, None)

    def test_eng_x_collabs(self):
        entry = as_node("""[2019.01.10] [[Carpet]] <small>([[Yesung]] x '''Bumkey''')</small>""")
        name = parse_generasia_name(entry)
        self.assertEqual(name.english, 'Carpet')
        self.assertEqual(name._english, 'Carpet')
        self.assertIs(name.non_eng, None)
        self.assertIs(name.korean, None)
        self.assertIs(name.japanese, None)
        self.assertIs(name.cjk, None)
        self.assertIs(name.romanized, None)
        self.assertIs(name.lit_translation, None)
        self.assertIs(name.extra, None)

    # def test_song_paren_ost(self):
    #     # TODO: Handle this case...
    #     entry = as_node('''[2013.12.01] [[Find Your Soul (Blade & Soul 2013 OST)]]''')
    #     name = parse_generasia_name(entry)
    #     self.assertEqual(name.english, 'Find Your Soul')
    #     self.assertEqual(name._english, 'Find Your Soul')
    #     self.assertIs(name.non_eng, None)
    #     self.assertIs(name.korean, None)
    #     self.assertIs(name.japanese, None)
    #     self.assertIs(name.cjk, None)
    #     self.assertIs(name.romanized, None)
    #     self.assertIs(name.lit_translation, None)
    #     self.assertIs(name.extra, 'Blade & Soul 2013 OST')

    # def test_ost_part_rom_incomplete_han_collabs(self):
    #     # TODO: Handle this
    #     entry = as_node("""[2015.10.31] [[Naegen Neomu Sarangseureoun Geunyeo OST Part 1]] (내겐 너무 사랑스러운 그녀) <small>([[LOCO]] & '''MAMAMOO''', [[Park Mi Young]])</small>""")
    #     name = parse_generasia_name(entry)
    #     self.assertIs(name.english, None)
    #     self.assertIs(name._english, None)
    #     self.assertIs(name.non_eng, '내겐 너무 사랑스러운 그녀')
    #     self.assertIs(name.korean, '내겐 너무 사랑스러운 그녀')
    #     self.assertIs(name.japanese, None)
    #     self.assertIs(name.cjk, None)
    #     self.assertIs(name.romanized, 'Naegen Neomu Sarangseureoun Geunyeo OST Part 1')
    #     self.assertIs(name.lit_translation, None)
    #     self.assertIs(name.extra, None)
    #
    # def test_ost_part_rom_incomplete_han_lit(self):
    #     # TODO: Not 100% sure how this case should be handled
    #     entry = as_node('''[2020.01.28] [[Nangmandagteo Kimsabu 2 OST Part 6]] (낭만닥터 김사부; ''Romantic Doctor'')''')
    #     name = parse_generasia_name(entry)
    #     self.assertEqual(name.english, 'Romantic Doctor')
    #     self.assertIs(name._english, None)
    #     self.assertEqual(name.non_eng, '낭만닥터 김사부')
    #     self.assertIs(name.korean, None)
    #     self.assertIs(name.japanese, None)
    #     self.assertIs(name.cjk, None)
    #     self.assertEqual(name.romanized, 'Nangmandagteo Kimsabu 2 OST Part 6')
    #     self.assertEqual(name.lit_translation, 'Romantic Doctor')
    #     self.assertIs(name.extra, None)

    # def test_artists_dash_album(self):
    #     # TODO: handle this
    #     entry = as_node("""[2010.05.20] [[2PM]] & '''Girls' Generation''' - [[Cabi Song]]""")
    #     name = parse_generasia_name(entry)
    #     self.assertEqual(name.english, 'Cabi Song')
    #     self.assertEqual(name._english, 'Cabi Song')
    #     self.assertIs(name.non_eng, None)
    #     self.assertIs(name.korean, None)
    #     self.assertIs(name.japanese, None)
    #     self.assertIs(name.cjk, None)
    #     self.assertIs(name.romanized, None)
    #     self.assertIs(name.lit_translation, None)
    #     self.assertIs(name.extra, None)

    # def test_(self):
    #     entry = as_node('''''')
    #     name = parse_generasia_name(entry)
    #     self.assertEqual(name.english, '')
    #     self.assertEqual(name._english, '')
    #     self.assertIs(name.non_eng, None)
    #     self.assertIs(name.korean, None)
    #     self.assertIs(name.japanese, None)
    #     self.assertIs(name.cjk, None)
    #     self.assertIs(name.romanized, None)
    #     self.assertIs(name.lit_translation, None)
    #     self.assertIs(name.extra, None)


if __name__ == '__main__':
    init_logging(0, log_path=None, names=None)
    try:
        unittest.main(warnings='ignore', verbosity=2, exit=False)
    except KeyboardInterrupt:
        print()
