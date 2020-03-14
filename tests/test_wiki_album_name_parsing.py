#!/usr/bin/env python

import logging
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.append(Path(__file__).parents[1].joinpath('lib').as_posix())
from wiki_nodes.nodes import as_node
from music_manager.wiki.parsing.generasia import parse_generasia_name
from music_manager.utils.test_common import NameTestCaseBase, main

log = logging.getLogger(__name__)


class GenerasiaAlbumNameParsingTest(NameTestCaseBase):
    def test_partial_romanized(self):
        entry = as_node("""Dallyeo! (Relay) (달려!; ''Run!'')""")
        entry.root = MagicMock(title='Dallyeo! (Relay)')
        name = parse_generasia_name(entry)
        self.assertAll(
            name, 'Run! (Relay)', None, '달려! (Relay)', '달려! (Relay)', romanized='Dallyeo! (Relay)',
            lit_translation='Run! (Relay)'
        )

    def test_rom_han_lit(self):
        entry = as_node("""[2007.11.01] [[So Nyeo Si Dae]] (소녀시대; ''Girls' Generation'')""")
        name = parse_generasia_name(entry)
        self.assertAll(
            name, 'Girls\' Generation', None, '소녀시대', '소녀시대', romanized='So Nyeo Si Dae',
            lit_translation='Girls\' Generation'
        )

    def test_eng_repackage(self):
        entry = as_node("""[2008.03.17] [[So Nyeo Si Dae|Baby Baby]] ''(Repackage Album)''""")
        name = parse_generasia_name(entry)
        self.assertAll(name, 'Baby Baby', 'Baby Baby', extra='Repackage Album')

    def test_eng_simple(self):
        entry = as_node("""[2010.01.28] [[Oh!]]""")
        name = parse_generasia_name(entry)
        self.assertAll(name, 'Oh!', 'Oh!')

    def test_rom_eng_han_lit(self):
        entry = as_node("""[2009.06.29] [[Sowoneul Malhaebwa (Genie)]] (소원을 말해봐; ''Tell Me Your Wish'')""")
        name = parse_generasia_name(entry)
        self.assertAll(
            name, 'Genie', 'Genie', '소원을 말해봐', '소원을 말해봐', romanized='Sowoneul Malhaebwa',
            lit_translation='Tell Me Your Wish'
        )

    def test_eng_alb_type(self):
        entry = as_node("""[2008.02.18] [[Sweet Memories With Girls' Generation|Sweet Memories with Girls' Generation]] ''(Song Selection Album)''""")
        name = parse_generasia_name(entry)
        en = 'Sweet Memories with Girls\' Generation'
        self.assertAll(name, en, en, extra='Song Selection Album')

    def test_rom_eng_han(self):
        entry = as_node("""[2007.08.02] [[Dasi Mannan Segye (Into the New World)|Dasi Mannan Segye (Into the new world)]] (다시 만난 세계)""")
        name = parse_generasia_name(entry)
        en, ko = 'Into the new world', '다시 만난 세계'
        self.assertAll(name, en, en, ko, ko, romanized='Dasi Mannan Segye')

    def test_rom_eng_remix_han(self):
        entry = as_node("""[2007.09.13] [[Dasi Mannan Segye (Into the New World)|Dasi Mannan Segye (Into the new world) Remix]] (다시 만난 세계)""")
        name = parse_generasia_name(entry)
        en, ko = 'Into the new world', '다시 만난 세계'
        self.assertAll(name, en, en, ko, ko, romanized='Dasi Mannan Segye', extra='Remix')

    def test_eng_parens(self):
        # "POP!POP!" should be part of the english name here...
        entry = as_node("""[2011.01.17] [[Visual Dreams (Pop!Pop!)|Visual Dreams (POP!POP!)]]""")
        name = parse_generasia_name(entry)
        self.assertAll(name, 'Visual Dreams (POP!POP!)', 'Visual Dreams (POP!POP!)')

    def test_rom_han(self):
        entry = as_node("""[2016.08.05] [[Geu Yeoleum]] (그 여름)""")
        name = parse_generasia_name(entry)
        self.assertAll(name, None, None, '그 여름', '그 여름', romanized='Geu Yeoleum')

    def test_ost_multiple_songs(self):
        entry = as_node("""[2007.11.23] [[Thirty Thousand Miles in Search of My Son OST]] ''(#1 Touch the Sky (Original Ver.), #13 Touch the Sky (Drama Ver.))''""")
        name = parse_generasia_name(entry)
        en = 'Thirty Thousand Miles in Search of My Son OST'
        self.assertAll(name, en, en, extra='#1 Touch the Sky (Original Ver.), #13 Touch the Sky (Drama Ver.)')

    def test_eng_album_plus_track(self):
        entry = as_node("""[2007.12.07] [[2007 Winter SMTown|2007 WINTER SMTOWN]] ''(#7 Lovely Melody)''""")
        name = parse_generasia_name(entry)
        self.assertAll(name, '2007 WINTER SMTOWN', '2007 WINTER SMTOWN', extra='#7 Lovely Melody')

    def test_eng_album_track_various_artists(self):
        entry = as_node("""[2007.12.13] [[Light]] ''(#1 Light (Various Artists))''""")
        name = parse_generasia_name(entry)
        self.assertAll(name, 'Light', 'Light', extra='#1 Light (Various Artists)')

    def test_eng_ost_track(self):
        entry = as_node("""[2008.01.22] [[Hong Gil Dong OST]] ''(#5 Jak Eun Bae)''""")
        name = parse_generasia_name(entry)
        self.assertAll(name, 'Hong Gil Dong OST', 'Hong Gil Dong OST', extra='#5 Jak Eun Bae')

    def test_eng_rom_artists(self):
        entry = as_node("""[2008.05.08] [[Haptic Motion]] (햅틱모션) <small>([[Jessica]], [[Yoona]], [[Tiffany]], [[Tong Vfang Xien Qi|Dong Bang Shin Ki]])</small>""")
        name = parse_generasia_name(entry)
        en, ko = 'Haptic Motion', '햅틱모션'
        self.assertAll(name, en, en, ko, ko)

    def test_primary_dash_eng_paren_track_paren_collabs(self):
        entry = as_node("""[2008.12.05] [[Yoon Sang]] - [[Song Book Play With Him|Song Book: Play With Him]] ''(#3 Lallalla ('''Girls' Generation''' + Yoon Sang))''""")
        name = parse_generasia_name(entry)
        en = 'Song Book: Play With Him'
        self.assertAll(name, en, en, extra='#3 Lallalla (Girls\' Generation + Yoon Sang)')

    def test_eng_with_parens_artists(self):
        entry = as_node("""[2009.12.15] [[Seoul (Seoul City Promotional Song)|SEOUL (Seoul City Promotional Song) ]] <small>([[Taeyeon]], [[Jessica]], [[Sunny]], [[Seohyun]], [[Kyuhyun]], [[Ryeowook]], [[Sungmin]], [[Donghae]])</small>""")
        name = parse_generasia_name(entry)
        en = 'SEOUL (Seoul City Promotional Song)'
        self.assertAll(name, en, en)

    def test_project_track_slash_collabs(self):
        # Note: the extras on this line have an extra trailing ''
        entry = as_node("""[2013.03.28] [[10 Corso Como Seoul Melody Collaboration Project|10 CORSO COMO SEOUL MELODY Collaboration Project]] (#1 ''Trick'' / '''Girls Generation''' x DJ Soul Scape'')""")
        name = parse_generasia_name(entry)
        en = '10 CORSO COMO SEOUL MELODY Collaboration Project'
        self.assertAll(name, en, en, extra='#1 Trick / Girls Generation x DJ Soul Scape')

    def test_eng_ost_han_no_ost(self):
        entry = as_node("""[2015.09.16] [[Innisia Nest OST]] (이니시아 네스트)""")
        name = parse_generasia_name(entry)
        en, ko = 'Innisia Nest OST', '이니시아 네스트'
        self.assertAll(name, en, en, ko, ko)

    def test_mixed_rom_han_lit(self):
        entry = as_node("""[2016.02.12] [[1cm Ui Jajonsim]] (1cm의 자존심; ''1cm Pride'')""")
        name = parse_generasia_name(entry)
        en, ko = '1cm Pride', '1cm의 자존심'
        self.assertAll(name, en, None, ko, ko, romanized='1cm Ui Jajonsim', lit_translation=en)

    def test_ost_part_rom_han_lit(self):
        entry = as_node("""[2017.03.24] [[Himssenyeoja Dobongsun OST Part 5]] (힘쎈여자 도봉순 OST Part 5; ''A Strong Woman OST Part 5'')""")
        name = parse_generasia_name(entry)
        en, ko = 'A Strong Woman OST Part 5', '힘쎈여자 도봉순 OST Part 5'
        self.assertAll(name, en, None, ko, ko, romanized='Himssenyeoja Dobongsun OST Part 5', lit_translation=en)

    def test_ost_part_eng_han(self):
        entry = as_node("""[2017.05.09] [[Man to Man OST Part 5]] (맨투맨 OST Part 5)""")
        name = parse_generasia_name(entry)
        en, ko = 'Man to Man OST Part 5', '맨투맨 OST Part 5'
        self.assertAll(name, en, en, ko, ko)

    def test_ost_part_eng(self):
        entry = as_node("""[2018.05.09] [[Suits OST Part 3]]""")
        name = parse_generasia_name(entry)
        self.assertAll(name, 'Suits OST Part 3', 'Suits OST Part 3')

    def test_rom_han_eng(self):
        entry = as_node("""[2018.07.01] [[Jangma]] (장마; ''Rainy Season'')""")
        name = parse_generasia_name(entry)
        self.assertAll(name, 'Rainy Season', None, '장마', '장마', romanized='Jangma', lit_translation='Rainy Season')

    def test_rom_han_eng_collabs(self):
        entry = as_node("""[2014.01.09] [[Haengbok Hajima]] (행복하지마; ''Don't Be Happy'') <small>('''mamamoo''' & [[Bumkey]])</small>""")
        name = parse_generasia_name(entry)
        en, ko = 'Don\'t Be Happy', '행복하지마'
        self.assertAll(name, en, None, ko, ko, romanized='Haengbok Hajima', lit_translation=en)

    def test_rom_han_eng_collabs_feat(self):
        entry = as_node("""[2014.02.11] [[Sseomnam Sseomnyeo]] (썸남썸녀; ''Peppermint Chocolate'') <small>([[K.Will]] & '''mamamoo''' ft. [[Wheesung]])</small>""")
        name = parse_generasia_name(entry)
        en, ko = 'Peppermint Chocolate', '썸남썸녀'
        self.assertAll(name, en, None, ko, ko, romanized='Sseomnam Sseomnyeo', lit_translation=en)

    def test_eng_han_collabs(self):
        entry = as_node("""[2014.05.30] [[Hi Hi Ha He Ho]] (히히하헤호) <small>('''MAMAMOO''' & [[Geeks]])</small>""")
        name = parse_generasia_name(entry)
        en, ko = 'Hi Hi Ha He Ho', '히히하헤호'
        self.assertAll(name, en, en, ko, ko)

    def test_eng_collabs(self):
        entry = as_node("""[2015.04.02] [[Ahh Oop!|AHH OOP!]] <small>('''MAMAMOO''' & [[eSNa]])</small>""")
        name = parse_generasia_name(entry)
        self.assertAll(name, 'AHH OOP!', 'AHH OOP!')

    def test_ost_rom_track(self):
        # Would prefer that this be captured as a romanization, but that would be tough
        entry = as_node("""[2014.08.29] [[Yeonaemalgo Gyeolhon OST]] (#2 ''Love Lane'')""")
        name = parse_generasia_name(entry)
        self.assertAll(name, 'Yeonaemalgo Gyeolhon OST', 'Yeonaemalgo Gyeolhon OST', extra='#2 Love Lane')

    def test_ost_rom_track_missing_num(self):
        # Would prefer that this be captured as a romanization, but that would be tough
        # This is really better suited to be tested as a full line parse test, rather than just the name
        entry = as_node("""[2014.11.06] [[Naegen Neomu Sarangseureoun Geunyeo OST]] (# ''I Norae'')""")
        name = parse_generasia_name(entry)
        en = 'Naegen Neomu Sarangseureoun Geunyeo OST'
        self.assertAll(name, en, en, extra='# I Norae')

    def test_ost_eng_track_rom_eng(self):
        entry = as_node("""[2015.03.12] [[Spy OST]] (#6 ''Nae Nun Sogen Neo (My Everything)'')""")
        name = parse_generasia_name(entry)
        self.assertAll(name, 'Spy OST', 'Spy OST', extra='#6 Nae Nun Sogen Neo (My Everything)')

    def test_competition_part_track(self):
        entry = as_node("""[2019.09.13] [[Queendom (Covergog Gyeongyeon) Part 1|Queendom [Covergog Gyeongyeon] Part 1]] (#1 ''Good Luck'')""")
        name = parse_generasia_name(entry)
        en = 'Queendom [Covergog Gyeongyeon] Part 1'
        self.assertAll(name, en, en, extra='#1 Good Luck')

    def test_competition_part_track_missing_num(self):
        entry = as_node("""[2019.10.18] [[Queendom (Pandoraui Sangja) Part 1|Queendom [Pandoraui Sangja] Part 1]] (# ''I Miss You'')""")
        name = parse_generasia_name(entry)
        en = 'Queendom [Pandoraui Sangja] Part 1'
        self.assertAll(name, en, en, extra='# I Miss You')

    def test_competition_track_rom_eng(self):
        entry = as_node("""[2019.10.25] [[Queendom (Final Comeback Single)|Queendom [FINAL Comeback Single]]] (#6 ''Urin Gyeolgug Dasi Mannal Unmyeongieossji (Destiny)'')""")
        name = parse_generasia_name(entry)
        en = 'Queendom [FINAL Comeback Single]'
        self.assertAll(name, en, en, extra='#6 Urin Gyeolgug Dasi Mannal Unmyeongieossji (Destiny)')

    def test_rom_han_eng_feat(self):
        entry = as_node("""[2012.01.20] [[Michinyeonae]] (미친연애; ''Bad Girl'') (feat. [[E-Sens]] of [[Supreme Team]])""")
        name = parse_generasia_name(entry)
        en, ko = 'Bad Girl', '미친연애'
        self.assertAll(name, en, None, ko, ko, romanized='Michinyeonae', lit_translation=en)

    def test_eng_x_collabs(self):
        entry = as_node("""[2019.01.10] [[Carpet]] <small>([[Yesung]] x '''Bumkey''')</small>""")
        name = parse_generasia_name(entry)
        self.assertAll(name, 'Carpet', 'Carpet')

    def test_ost_part_rom_incomplete_han_collabs(self):
        entry = as_node("""[2015.10.31] [[Naegen Neomu Sarangseureoun Geunyeo OST Part 1]] (내겐 너무 사랑스러운 그녀) <small>([[LOCO]] & '''MAMAMOO''', [[Park Mi Young]])</small>""")
        name = parse_generasia_name(entry)
        ko = '내겐 너무 사랑스러운 그녀'
        self.assertAll(name, None, None, ko, ko, romanized='Naegen Neomu Sarangseureoun Geunyeo OST Part 1')

    def test_ost_part_rom_incomplete_han_lit(self):
        # TODO: Not 100% sure how this case should be handled
        entry = as_node("""[2020.01.28] [[Nangmandagteo Kimsabu 2 OST Part 6]] (낭만닥터 김사부; ''Romantic Doctor'')""")
        name = parse_generasia_name(entry)
        en, ko = 'Romantic Doctor', '낭만닥터 김사부'
        self.assertAll(name, en, None, ko, ko, romanized='Nangmandagteo Kimsabu 2 OST Part 6', lit_translation=en)

    def test_song_paren_ost(self):
        entry = as_node("""[2013.12.01] [[Find Your Soul (Blade & Soul 2013 OST)]]""")
        name = parse_generasia_name(entry)
        self.assertAll(name, 'Find Your Soul', 'Find Your Soul', extra='Blade & Soul 2013 OST')

    def test_artists_dash_album(self):
        entry = as_node("""[2010.05.20] [[2PM]] & '''Girls' Generation''' - [[Cabi Song]]""")
        name = parse_generasia_name(entry)
        self.assertAll(name, 'Cabi Song', 'Cabi Song')


if __name__ == '__main__':
    main(GenerasiaAlbumNameParsingTest)
