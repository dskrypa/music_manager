#!/usr/bin/env python

import logging
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.append(Path(__file__).parents[1].joinpath('lib').as_posix())
from wiki_nodes.nodes import as_node, Link
from music.test_common import NameTestCaseBase, main
from music.text.name import Name
from music.wiki.album import DiscographyEntry
from music.wiki.parsing.generasia import GenerasiaParser
from music.wiki.parsing.kpop_fandom import KpopFandomParser
from music.wiki.track import Track

log = logging.getLogger(__name__)

parse_generasia_track_name = GenerasiaParser.parse_track_name
parse_kf_track_name = KpopFandomParser.parse_track_name


class KpopFandomTrackNameParsingTest(NameTestCaseBase):
    _site = 'kpop.fandom.com'
    _interwiki_map = {'w': 'https://community.fandom.com/wiki/$1'}
    root = MagicMock(site=_site, _interwiki_map=_interwiki_map)

    def test_link_title(self):
        entry = as_node(""""[[Black Swan]]" - 3:18""", root=self.root)
        name = parse_kf_track_name(entry)
        eng, han = 'Black Swan', None
        self.assertAll(name, eng, eng, han, han, extra={'length': '3:18'})

    def test_time_in_title(self):
        entry = as_node(""""00:00 (Zero O'Clock)" - 4:10""", root=self.root)
        name = parse_kf_track_name(entry)
        eng, han = '00:00 (Zero O\'Clock)', None
        self.assertAll(name, eng, eng, han, han, extra={'length': '4:10'})

    def test_lang_ver_in_quotes(self):
        entry = as_node(""""Jump (Japanese ver.)" - 3:57""", root=self.root)
        name = parse_kf_track_name(entry)
        eng, han = 'Jump', None
        self.assertAll(name, eng, eng, han, han, extra={'length': '3:57', 'version': 'Japanese ver.'})

    def test_multi_meta_in_quotes(self):
        entry = as_node(""""Just One Day (Japanese ver.) (Extended play)" - 5:33""", root=self.root)
        name = parse_kf_track_name(entry)
        eng, han = 'Just One Day', None
        self.assertAll(
            name, eng, eng, han, han, extra={'length': '5:33', 'version': 'Japanese ver.', 'misc': 'Extended play'}
        )

    def test_multi_enclosed_in_quotes(self):
        entry = as_node(""""I Like It! Pt.2 ~In That Place~ (いいね! Pt.2 ～あの場所で～)" - 3:55""", root=self.root)
        name = parse_kf_track_name(entry)
        eng, non_eng = 'I Like It! Pt.2 (In That Place)', 'いいね! Pt.2 ～あの場所で～'
        self.assertAll(name, eng, eng, non_eng, cjk=non_eng, japanese=non_eng, extra={'length': '3:55'})

    def test_duet_links(self):
        entry = as_node(""""Moonlight (월광)" ([[Baekhyun]] & [[D.O.]] duet) - 4:26""", root=self.root)
        name = parse_kf_track_name(entry)
        eng, han = 'Moonlight', '월광'
        artists = as_node("""[[Baekhyun]] & [[D.O.]]""", root=self.root)
        self.assertAll(name, eng, eng, han, han, extra={'length': '4:26', 'artists': artists})

    def test_feat_no_link(self):
        entry = as_node(""""BTS Cypher Pt.3: Killer" (feat. Supreme Boi) - 4:28""", root=self.root)
        name = parse_kf_track_name(entry)
        eng, han = 'BTS Cypher Pt.3: Killer', None
        self.assertAll(name, eng, eng, han, han, extra={'length': '4:28', 'feat': 'Supreme Boi'})

    def test_numeric_title(self):
        entry = as_node(""""134340" - 3:49""", root=self.root)
        name = parse_kf_track_name(entry)
        eng, han = '134340', None
        self.assertAll(name, eng, eng, han, han, extra={'length': '3:49'})

    def test_sung_by_list(self):
        entry = as_node(""""Hair in the Air" (Sung By [[Yeri (Red Velvet)|Yeri]], [[Renjun]], [[Jeno]], [[Jaemin]]) - 2:47""", root=self.root)
        name = parse_kf_track_name(entry)
        eng, han = 'Hair in the Air', None
        artists = as_node("""[[Yeri (Red Velvet)|Yeri]] , [[Renjun]] , [[Jeno]] , [[Jaemin]]""", root=self.root)
        self.assertAll(name, eng, eng, han, han, extra={'length': '2:47', 'artists': artists})

    def test_inst_eng(self):
        entry = as_node(""""Wow Thing (Inst.)" - 2:52""", root=self.root)
        name = parse_kf_track_name(entry)
        eng, han = 'Wow Thing', None
        self.assertAll(name, eng, eng, han, han, extra={'length': '2:52', 'instrumental': True})

    def test_multi_enclosed_with_lang(self):
        entry = as_node(""""Hanabi (Remember Me) (花火)" <small>(Japanese ver.)</small> - 3:14""", root=self.root)
        name = parse_kf_track_name(entry)
        eng, non_eng, rom = 'Remember Me', '花火', 'Hanabi'
        self.assertAll(
            name, eng, eng, non_eng, cjk=non_eng, romanized=rom,
            extra={'length': '3:14', 'version': 'Japanese ver.'}
        )

    def test_artist_link_list_feat_no_link(self):
        entry = as_node(""""White (화이트)" <small>([[OH MY GIRL]], [[Haha]] feat. M.TySON)</small> - 3:35""", root=self.root)
        name = parse_kf_track_name(entry)
        eng, han = 'White', '화이트'
        artists = as_node("""[[OH MY GIRL]] , [[Haha]]""", root=self.root)
        self.assertAll(name, eng, eng, han, han, extra={'length': '3:35', 'artists': artists, 'feat': 'M.TySON'})

    def test_nested_enclosed(self):
        entry = as_node(""""Face to Face (After Looking At You) (마주보기 (바라보기 그 후))" - 3:23""", root=self.root)
        name = parse_kf_track_name(entry)
        eng, han = 'Face to Face (After Looking At You)', '마주보기 (바라보기 그 후)'
        self.assertAll(name, eng, eng, han, han, extra={'length': '3:23'})

    def test_acoustic_ver(self):
        entry = as_node(""""Lost Child (미아) (Acoustic Ver.)" - 3:47""", root=self.root)
        name = parse_kf_track_name(entry)
        eng, han = 'Lost Child', '미아'
        self.assertAll(name, eng, eng, han, han, extra={'length': '3:47', 'acoustic': True})

    def test_rock_ver(self):
        entry = as_node(""""You Know (있잖 아) (Rock Ver.)" - 3:10""", root=self.root)
        name = parse_kf_track_name(entry)
        eng, han = 'You Know', '있잖 아'
        self.assertAll(name, eng, eng, han, han, extra={'length': '3:10', 'version': 'Rock Ver.'})

    def test_inst_mix(self):
        entry = as_node(""""Pitiful (가여워) (Inst.)" - 3:20""", root=self.root)
        name = parse_kf_track_name(entry)
        eng, han = 'Pitiful', '가여워'
        self.assertAll(name, eng, eng, han, han, extra={'length': '3:20', 'instrumental': True})

    def test_parenthetical_mix(self):
        entry = as_node(""""Between the Lips (50cm) (입술 사이)" - 2:50""", root=self.root)
        name = parse_kf_track_name(entry)
        eng, han = 'Between the Lips (50cm)', '입술 사이'
        self.assertAll(name, eng, eng, han, han, extra={'length': '2:50'})

    def test_from_ost(self):
        entry = as_node(""""Pastel Crayon (크레파스)" (Bel Ami OST) - 3:13""", root=self.root)
        name = parse_kf_track_name(entry)
        eng, han = 'Pastel Crayon', '크레파스'
        self.assertAll(name, eng, eng, han, han, extra={'length': '3:13', 'album': 'Bel Ami OST'})

    def test_non_eng_non_romanization_eng(self):
        entry = as_node('''"Dlwlrma (이 지금)"''', root=self.root)
        name = parse_kf_track_name(entry)
        eng, han = 'Dlwlrma', '이 지금'
        self.assertAll(name, eng, eng, han, han)

    def test_french_eng(self):
        entry = as_node(""""Jamais Vu" - 3:46""", root=self.root)
        name = parse_kf_track_name(entry)
        eng, han = 'Jamais Vu', None
        self.assertAll(name, eng, eng, han, han, extra={'length': '3:46'})

    def test_feat_singer_of_group(self):
        entry = as_node(""""거짓말" (feat. [[Lee Hae Ri]] of [[Davichi]])""", root=self.root)
        name = parse_kf_track_name(entry)
        eng, han = None, '거짓말'
        feat = as_node("""[[Lee Hae Ri]] of [[Davichi]]""", root=self.root)
        self.assertAll(name, eng, eng, han, han, extra={'feat': feat})

    def test_feat_interwiki(self):
        entry = as_node(""""Lost Without You (우리집을 못 찾겠군요)" (feat. [[w:c:kindie:Bolbbalgan4|Bolbbalgan4]])""", root=self.root)
        name = parse_kf_track_name(entry)
        eng, han = 'Lost Without You', '우리집을 못 찾겠군요'
        feat = as_node("""[[w:c:kindie:Bolbbalgan4|Bolbbalgan4]]""", root=self.root)
        self.assertAll(name, eng, eng, han, han, extra={'feat': feat})

    def test_remix_feat_no_link(self):
        entry = as_node(""""나쁜 피 (Common Cold Remix)" (feat. Justhis)""", root=self.root)
        name = parse_kf_track_name(entry)
        eng, han = None, '나쁜 피'
        self.assertAll(name, eng, eng, han, han, extra={'remix': 'Common Cold Remix', 'feat': 'Justhis'})

    def test_track_1(self):
        entry = as_node(""""Intro : Persona" - 2:54""", root=self.root)
        name = parse_kf_track_name(entry)
        eng, han = 'Intro: Persona', None
        self.assertAll(name, eng, eng, han, han, extra={'length': '2:54'})

    def test_track_2(self):
        entry = as_node(""""Boy With Luv (작은 것들을 위한 시)" (feat. [[wikipedia:Halsey (singer)|Halsey]]) - 3:49""", root=self.root)
        name = parse_kf_track_name(entry)
        eng, han = 'Boy With Luv', '작은 것들을 위한 시'
        feat = as_node("""[[wikipedia:Halsey (singer)|Halsey]]""", root=self.root)
        self.assertAll(name, eng, eng, han, han, extra={'length': '3:49', 'feat': feat})

    def test_track_3(self):
        entry = as_node(""""My Time (시차)" - 3:54""", root=self.root)
        name = parse_kf_track_name(entry)
        eng, han = 'My Time', '시차'
        self.assertAll(name, eng, eng, han, han, extra={'length': '3:54'})

    def test_track_4(self):
        entry = as_node(""""Ugh! (욱)" - 3:45""", root=self.root)
        name = parse_kf_track_name(entry)
        eng, han = 'Ugh!', '욱'
        self.assertAll(name, eng, eng, han, han, extra={'length': '3:45'})

    def test_track_5(self):
        entry = as_node(""""On" (feat. [[Wikipedia:Sia (musician)|Sia]]) - 4:06 {{small| 1 = ('''Digital only''')}}""", root=self.root)
        name = parse_kf_track_name(entry)
        eng, han = 'On', None
        feat = as_node("""[[Wikipedia:Sia (musician)|Sia]]""", root=self.root)
        self.assertAll(name, eng, eng, han, han, extra={'length': '4:06', 'feat': feat, 'availability': 'Digital only'})

    def test_track_6(self):
        entry = as_node(""""Run" - 3:57 <small>(Japanese version)</small>""", root=self.root)
        name = parse_kf_track_name(entry)
        eng, han = 'Run', None
        self.assertAll(name, eng, eng, han, han, extra={'length': '3:57', 'version': 'Japanese version'})

    def test_track_7(self):
        entry = as_node(""""Dope (超ヤベー!)" - 4:17 <small>(Japanese version)</small>""", root=self.root)
        name = parse_kf_track_name(entry)
        eng, non_eng = 'Dope', '超ヤベー!'
        self.assertAll(name, eng, eng, non_eng, japanese=non_eng, extra={'length': '4:17', 'version': 'Japanese version'})

    def test_track_8(self):
        entry = as_node(""""Epilogue: Young Forever" - 2:53 <small>(Japanese version)</small>""", root=self.root)
        name = parse_kf_track_name(entry)
        eng, han = 'Epilogue: Young Forever', None
        self.assertAll(name, eng, eng, han, han, extra={'length': '2:53', 'version': 'Japanese version'})

    def test_track_9(self):
        entry = as_node(""""N.O (Japanese ver.)" - 3:31""", root=self.root)
        name = parse_kf_track_name(entry)
        eng, han = 'N.O', None
        self.assertAll(name, eng, eng, han, han, extra={'length': '3:31', 'version': 'Japanese ver.'})

    def test_track_10(self):
        entry = as_node(""""Baby Don't Cry (인어의 눈물)" - 3:55""", root=self.root)
        name = parse_kf_track_name(entry)
        eng, han = 'Baby Don\'t Cry', '인어의 눈물'
        self.assertAll(name, eng, eng, han, han, extra={'length': '3:55'})

    def test_track_11(self):
        entry = as_node(""""Black Pearl" - 3:08""", root=self.root)
        name = parse_kf_track_name(entry)
        eng, han = 'Black Pearl', None
        self.assertAll(name, eng, eng, han, han, extra={'length': '3:08'})

    def test_track_12(self):
        entry = as_node(""""3.6.5" - 3:07""", root=self.root)
        name = parse_kf_track_name(entry)
        eng, han = '3.6.5', None
        self.assertAll(name, eng, eng, han, han, extra={'length': '3:07'})

    def test_track_13(self):
        entry = as_node(""""Wolf (늑대와 미녀)" (EXO-K ver.) - 3:52""", root=self.root)
        name = parse_kf_track_name(entry)
        eng, han = 'Wolf', '늑대와 미녀'
        self.assertAll(name, eng, eng, han, han, extra={'length': '3:52', 'version': 'EXO-K ver.'})

    def test_track_14(self):
        entry = as_node(""""Wolf (狼与美女)" (Mandarin ver.) - 3:52""", root=self.root)
        name = parse_kf_track_name(entry)
        eng, non_eng = 'Wolf', '狼与美女'
        self.assertAll(name, eng, eng, non_eng, cjk=non_eng, extra={'length': '3:52', 'version': 'Mandarin ver.'})

    def test_track_15(self):
        entry = as_node(""""Wolf (狼与美女)" - 3:52""", root=self.root)
        name = parse_kf_track_name(entry)
        eng, non_eng = 'Wolf', '狼与美女'
        self.assertAll(name, eng, eng, non_eng, cjk=non_eng, extra={'length': '3:52'})

    def test_track_16(self):
        entry = as_node(""""Wolf (늑대와 미녀)" (Korean ver.) - 3:52""", root=self.root)
        name = parse_kf_track_name(entry)
        eng, han = 'Wolf', '늑대와 미녀'
        self.assertAll(name, eng, eng, han, han, extra={'length': '3:52', 'version': 'Korean ver.'})

    def test_track_17(self):
        entry = as_node(""""Love, Love, Love" - 3:55""", root=self.root)
        name = parse_kf_track_name(entry)
        eng, han = 'Love, Love, Love', None
        self.assertAll(name, eng, eng, han, han, extra={'length': '3:55'})

    def test_track_18(self):
        entry = as_node(""""Overdose (중독)" (EXO version) - 3:25 <small>('''CD only''')</small>""", root=self.root)
        name = parse_kf_track_name(entry)
        eng, han = 'Overdose', '중독'
        self.assertAll(name, eng, eng, han, han, extra={'length': '3:25', 'version': 'EXO version', 'availability': 'CD only'})

    def test_track_20(self):
        entry = as_node(""""Oh My God" <small>(English ver.)</small> - 3:15""", root=self.root)
        name = parse_kf_track_name(entry)
        eng, han = 'Oh My God', None
        self.assertAll(name, eng, eng, han, han, extra={'length': '3:15', 'version': 'English ver.'})

    def test_track_21(self):
        entry = as_node('''"Seoul"''', root=self.root)
        name = parse_kf_track_name(entry)
        eng, han = 'Seoul', None
        self.assertAll(name, eng, eng, han, han)

    def test_track_22(self):
        entry = as_node(""""Bad Bye" (with [[eAeon]])""", root=self.root)
        name = parse_kf_track_name(entry)
        eng, han = 'Bad Bye', None
        self.assertAll(name, eng, eng, han, han, extra={'collabs': as_node("""[[eAeon]]""", root=self.root)})

    def test_track_23(self):
        entry = as_node(""""Everythingoes (지나가)"  (with [[Nell]])""", root=self.root)
        name = parse_kf_track_name(entry)
        eng, han = 'Everythingoes', '지나가'
        self.assertAll(name, eng, eng, han, han, extra={'collabs': as_node("""[[Nell]]""", root=self.root)})

    def test_track_24(self):
        entry = as_node(""""Coloring Book" <small>(Japanese ver.)</small> - 3:07""", root=self.root)
        name = parse_kf_track_name(entry)
        eng, han = 'Coloring Book', None
        self.assertAll(name, eng, eng, han, han, extra={'length': '3:07', 'version': 'Japanese ver.'})

    def test_track_25(self):
        entry = as_node(""""Remember Me (불꽃놀이)" - 3:14 <small>('''Regular / Limited edition only''')</small>""", root=self.root)
        name = parse_kf_track_name(entry)
        eng, han = 'Remember Me', '불꽃놀이'
        self.assertAll(name, eng, eng, han, han, extra={'length': '3:14', 'availability': 'Regular / Limited edition only'})

    def test_track_26(self):
        entry = as_node(""""Windy Day" - 4:09 <small>('''Limited edition only''')</small>""", root=self.root)
        name = parse_kf_track_name(entry)
        eng, han = 'Windy Day', None
        self.assertAll(name, eng, eng, han, han, extra={'length': '4:09', 'availability': 'Limited edition only'})

    def test_track_27(self):
        entry = as_node(""""Always Winter (언제나 겨울)" <small>([[Skull (singer)|Skull]])</small> - 3:11""", root=self.root)
        name = parse_kf_track_name(entry)
        eng, han = 'Always Winter', '언제나 겨울'
        self.assertAll(
            name, eng, eng, han, han,
            extra={'length': '3:11', 'artists': as_node("""[[Skull (singer)|Skull]]""", root=self.root)}
        )

    def test_track_28(self):
        entry = as_node(""""You Know (있잖 아)" (Feat. [[Mario]]) - 3:21""", root=self.root)
        name = parse_kf_track_name(entry)
        eng, han = 'You Know', '있잖 아'
        self.assertAll(
            name, eng, eng, han, han, extra={'length': '3:21', 'feat': as_node("""[[Mario]]""", root=self.root)}
        )

    def test_track_29(self):
        entry = as_node(""""Voice Mail (Korean ver.)" (Bonus track) - 4:06""", root=self.root)
        name = parse_kf_track_name(entry)
        eng, han = 'Voice Mail', None
        self.assertAll(
            name, eng, eng, han, han, extra={'length': '4:06', 'version': 'Korean ver.', 'misc': 'Bonus track'}
        )

    def test_track_30(self):
        entry = as_node(""""[[Can't Love You Anymore]] (사랑이 잘)" (with [[w:c:kindie:Oh Hyuk|Oh Hyuk]])""", root=self.root)
        name = parse_kf_track_name(entry)
        eng, han = 'Can\'t Love You Anymore', '사랑이 잘'
        self.assertAll(
            name, eng, eng, han, han, extra={'collabs': as_node("""[[w:c:kindie:Oh Hyuk|Oh Hyuk]]""", root=self.root)}
        )

    def test_track_31(self):
        entry = as_node('''"Jam Jam (잼잼)"''', root=self.root)
        name = parse_kf_track_name(entry)
        eng, han = 'Jam Jam', '잼잼'
        self.assertAll(name, eng, eng, han, han)

    def test_track_32(self):
        entry = as_node('''"Full Stop (마침표)"''', root=self.root)
        name = parse_kf_track_name(entry)
        eng, han = 'Full Stop', '마침표'
        self.assertAll(name, eng, eng, han, han)

    def test_track_33(self):
        entry = as_node('''"[[Through the Night]] (밤편지)"''', root=self.root)
        name = parse_kf_track_name(entry)
        eng, han = 'Through the Night', '밤편지'
        self.assertAll(name, eng, eng, han, han)

    def test_track_34(self):
        entry = as_node(""""Zezé" - 3:10""", root=self.root)
        name = parse_kf_track_name(entry)
        eng, han = 'Zezé', None
        self.assertAll(name, eng, eng, han, han, extra={'length': '3:10'})

    def test_track_35(self):
        entry = as_node(""""Heart (마음)" <small>('''CD only''')</small> - 2:47""", root=self.root)
        name = parse_kf_track_name(entry)
        eng, han = 'Heart', '마음'
        self.assertAll(name, eng, eng, han, han, extra={'length': '2:47', 'availability': 'CD only'})

    def test_track_36(self):
        entry = as_node(""""Twenty Three" <small>('''CD only''')</small> - 3:30""", root=self.root)
        name = parse_kf_track_name(entry)
        eng, han = 'Twenty Three', None
        self.assertAll(name, eng, eng, han, han, extra={'length': '3:30', 'availability': 'CD only'})

    def test_track_37(self):
        entry = as_node(""""Only I Didn't Know (나만 몰랐던 이야기)" <small>(with [[Kim Kwang Min]])</small>""", root=self.root)
        name = parse_kf_track_name(entry)
        eng, han = 'Only I Didn\'t Know', '나만 몰랐던 이야기'
        self.assertAll(name, eng, eng, han, han, extra={'collabs': as_node("""[[Kim Kwang Min]]""", root=self.root)})

    def test_unpaired_quote(self):
        entry = as_node(""""A Song From The Past (이 노랜 꽤 오래된 거야) - 3:55""", root=self.root)
        name = parse_kf_track_name(entry)
        self.assertNamesEqual(name, Name('A Song From The Past', '이 노랜 꽤 오래된 거야', extra={'length': '3:55'}))

    def test_acoustic_rnb_version(self):
        entry = as_node(""""☆★☆''' (별별별)'''" '''(Acoustic R&B Version)''' - 4:28""", root=self.root)
        name = parse_kf_track_name(entry)
        self.assertNamesEqual(name, Name('☆★☆', '별별별', extra={'length': '4:28', 'version': 'Acoustic R&B Version'}))

    def test_eng_cjk_feat(self):
        entry = as_node(""""Winter Flower (雪中梅) (feat. [[RM]])" - 3:41""", root=self.root)
        name = parse_kf_track_name(entry)
        self.assertNamesEqual(
            name,
            Name('Winter Flower', '雪中梅', extra={'length': '3:41', 'feat': as_node("""[[RM]]""", root=self.root)})
        )

    def test_dash_enclosed_japanese_ver(self):
        entry = as_node(""""[[BBoom BBoom (single)|BBoom BBoom -Japanese ver.-]]" - 3:30""", root=self.root)
        name = parse_kf_track_name(entry)
        self.assertNamesEqual(name, Name('BBoom BBoom', extra={'length': '3:30', 'version': 'Japanese ver.'}))

    def test_multiple_versions(self):
        entry = as_node(""""Wonderful Love (EDM Version) -Japanese ver.-" - 3:26""", root=self.root)
        name = parse_kf_track_name(entry)
        self.assertNamesEqual(
            name, Name('Wonderful Love', extra={'length': '3:26', 'version': ['EDM Version', 'Japanese ver.']})
        )

    def test_feat_link_inside_quotes(self):
        entry = as_node(""""Starry Night (feat. [[Crush (singer)|Crush]])" - 3:31""", root=self.root)
        name = parse_kf_track_name(entry)
        self.assertNamesEqual(
            name, Name('Starry Night', extra={
                'length': '3:31', 'feat': as_node("""[[Crush (singer)|Crush]]""", root=self.root)
            })
        )

    def test_single_feat(self):
        page = self._fake_page(
            """"'''Eight'''" (에잇) is the seventh digital single by [[IU]]. It was released on May 6, 2020 and features [[Suga]].""",
            """{{Infobox single\n| name        = Eight\n| artist      = [[IU]] {{small\n|(feat. [[Suga]])\n}}\n| released    = May 6, 2020\n| length      = 2:47\n}}""",
            title='Eight',
            categories={'single article stubs', 'singles', 'digital singles', 'iu', '2020 releases', '2020 digital singles'}
        )
        de = DiscographyEntry('Eight', {self._site: page})
        parts = list(de.parts())
        self.assertEqual(len(parts), 1)
        part = parts[0]
        tracks = part.tracks
        self.assertEqual(len(tracks), 1)
        track = tracks[0]
        self.assertNamesEqual(
            track.name, Name('Eight', '에잇', extra={'length': '2:47', 'feat': Link.from_title('Suga', page)})
        )
        self.assertEqual(track.full_name(), 'Eight (에잇) (feat. Suga (슈가))')


class KpopFandomTrackNameReprTest(NameTestCaseBase):
    _site = 'kpop.fandom.com'
    _interwiki_map = {'w': 'https://community.fandom.com/wiki/$1'}
    root = MagicMock(site=_site, _interwiki_map=_interwiki_map)

    def test_feat_interwiki_repr(self):
        entry = as_node(""""Lost Without You (우리집을 못 찾겠군요)" (feat. [[w:c:kindie:Bolbbalgan4|Bolbbalgan4]])""", root=self.root)
        track = Track(3, parse_kf_track_name(entry), None)
        self.assertEqual(track.full_name(collabs=True), 'Lost Without You (우리집을 못 찾겠군요) (feat. BOL4 (볼빨간사춘기))')

    def test_track_artists_repr(self):
        entry = as_node(""""Someday" ([[Jinho]] & [[Hui (PENTAGON)|Hui]] duet) - 3:57""", root=self.root)
        track = Track(10, parse_kf_track_name(entry), None)
        self.assertEqual(track.full_name(collabs=True), 'Someday (Jinho (진호) & Hui (후이) duet)')

    def test_track_artist_solo_repr(self):
        entry = as_node(""""Be Calm (덤덤해지네)" ([[Hwa Sa]] solo) - 3:28""", root=self.root)
        name = parse_kf_track_name(entry)
        eng, han = 'Be Calm', '덤덤해지네'
        self.assertAll(
            name, eng, eng, han, han, extra={'artists': as_node("""[[Hwa Sa]]""", root=self.root), 'length': '3:28'}
        )
        track = Track(4, name, None)
        self.assertEqual(track.full_name(collabs=True), 'Be Calm (덤덤해지네) (Hwa Sa (화사) solo)')

    def test_multiple_versions_repr(self):
        name = Name('Wonderful Love', extra={'length': '3:26', 'version': ['EDM Version', 'Japanese ver.']})
        track = Track(7, name, None)
        self.assertEqual(track.full_name(collabs=True), 'Wonderful Love (EDM Version) (Japanese ver.)')


class GenerasiaTrackNameReprTest(NameTestCaseBase):
    _site = 'www.generasia.com'
    _interwiki_map = {}
    root = MagicMock(site=_site, _interwiki_map=_interwiki_map)
    # These feat tests are not ideal because they need to pull info from the wiki to look up the artist names, rather
    # than being fully self-contained.

    def test_feat_solo_of_group(self):
        entry = as_node("""[[Selfish (Moonbyul)|SELFISH]] (feat. [[Seulgi]] of [[Red Velvet]]) """, root=self.root)
        track = Track(6, parse_generasia_track_name(entry), None)
        self.assertEqual(track.full_name(collabs=True), 'SELFISH (feat. Seulgi (슬기) of Red Velvet (레드벨벳))')

    def test_feat_solo_paren_group(self):
        entry = as_node("""[[Hwaseongin Baireoseu (Boys & Girls)]] (feat. [[Key]] ([[SHINee]])) (화성인 바이러스; ''Martian Virus'')""", root=self.root)
        track = Track(9, parse_generasia_track_name(entry), None)
        expected = 'Boys & Girls (화성인 바이러스) (feat. Key (키) (SHINee (샤이니)))'
        self.assertEqual(track.full_name(collabs=True), expected)

    def test_remix_feat_repr(self):
        entry = as_node("""[[Bad Girl (Girls' Generation)|BAD GIRL (The Cataracs Remix)]] feat. [[DEV]]""", root=self.root)
        track = Track(3, parse_generasia_track_name(entry), None)
        expected = 'BAD GIRL (The Cataracs Remix) (feat. DEV)'
        self.assertEqual(track.full_name(collabs=True), expected)


class GenerasiaTrackNameParsingTest(NameTestCaseBase):
    _site = 'www.generasia.com'
    _interwiki_map = {}
    root = MagicMock(site=_site, _interwiki_map=_interwiki_map)

    def test_lit_slash_eng(self):
        entry = as_node("""[[Neona Hae]] (너나 해; ''You Do It'' / ''Egotistic'')""")
        name = parse_generasia_track_name(entry)
        self.assertAll(
            name, 'Egotistic', 'Egotistic', '너나 해', '너나 해', romanized='Neona Hae', lit_translation='You Do It'
        )

    def test_rom_han_eng(self):
        entry = as_node("""[[Yeoreumbamui Kkum]] (여름밤의 꿈; ''Midnight Summer Dream'')""")
        name = parse_generasia_track_name(entry)
        eng, han = 'Midnight Summer Dream', '여름밤의 꿈'
        self.assertAll(name, eng, None, han, han, romanized='Yeoreumbamui Kkum', lit_translation=eng)

    def test_rom_han_eng_with_parens(self):
        entry = as_node("""[[Haneulhaneul (Cheongsun)]] (하늘하늘 (청순); ''Sky! Sky! (Innocence)'')""")
        name = parse_generasia_track_name(entry)
        eng, han = 'Sky! Sky! (Innocence)', '하늘하늘 (청순)'
        self.assertAll(name, eng, None, han, han, romanized='Haneulhaneul (Cheongsun)', lit_translation=eng)

    def test_eng_feat(self):
        entry = as_node("""[[The Boys (Girls' Generation single)|The Boys "Bring Dem Boys"]] feat. Suzi""")
        name = parse_generasia_track_name(entry)
        self.assertAll(name, 'The Boys "Bring Dem Boys"', 'The Boys "Bring Dem Boys"', extra={'feat': 'Suzi'})

    def test_eng_other(self):
        entry = as_node("""[[Lazy Girl (Dolce Far Niente)]]""")
        name = parse_generasia_track_name(entry)
        self.assertAll(name, english='Lazy Girl (Dolce Far Niente)', romanized='Lazy Girl (Dolce Far Niente)')

    def test_unclosed_paren(self):
        entry = as_node("""[[The Boys (Girls' Generation single)|The Boys (Clinton Sparks & Disco Fries Remix]] feat. Snoop Dogg""")
        name = parse_generasia_track_name(entry)
        self.assertAll(
            name, 'The Boys', 'The Boys', extra={'remix': 'Clinton Sparks & Disco Fries Remix', 'feat': 'Snoop Dogg'}
        )

    def test_eng_version(self):
        entry = as_node("""[[The Boys (Girls' Generation single)|The Boys (Korean Version)]]""")
        name = parse_generasia_track_name(entry)
        self.assertAll(name, 'The Boys', 'The Boys', extra={'version': 'Korean Version'})

    def test_eng_remix(self):
        entry = as_node("""[[The Boys (Girls' Generation single)|The Boys "Bring The Boys Out" (David Anthony Remix)]]""")
        name = parse_generasia_track_name(entry)
        eng = 'The Boys "Bring The Boys Out"'
        self.assertAll(name, eng, eng, extra={'remix': 'David Anthony Remix'})

    def test_rom_inst(self):
        entry = as_node("""[[Neona Hae|Neona Hae (Inst.)]]""")
        name = parse_generasia_track_name(entry)
        self.assertAll(name, 'Neona Hae', romanized='Neona Hae', extra={'instrumental': True})

    def test_rom_han_eng_with_feat(self):
        entry = as_node("""[[Selfish (Moonbyul)|SELFISH]] (feat. [[Seulgi]] of [[Red Velvet]])""")
        name = parse_generasia_track_name(entry)
        self.assertAll(name, 'SELFISH', 'SELFISH', extra={'feat': as_node('[[Seulgi]] of [[Red Velvet]]')})

    def test_digital_edition(self):
        entry = as_node("""[[The Boys (Girls' Generation single)|The Boys (English Ver.)]] ''(Digital Ed. Only)''""")
        name = parse_generasia_track_name(entry)
        self.assertAll(name, 'The Boys', 'The Boys', extra={'version': 'English Ver.', 'edition': 'Digital Ed. Only'})

    def test_lang_ver_no_space(self):
        entry = as_node("""[[Hip|HIP-Japanese ver.-]]""")
        name = parse_generasia_track_name(entry)
        self.assertAll(name, 'HIP', 'HIP', extra={'version': 'Japanese ver.'})

    def test_cjk_eng_rom_lit(self):
        entry = as_node("""[[Wolf (EXO)|Lang Yu Meinu (Wolf)]] (狼与美女; ''Wolf and the Beauty'')""")
        name = parse_generasia_track_name(entry)
        self.assertAll(
            name, 'Wolf', 'Wolf', '狼与美女', cjk='狼与美女', romanized='Lang Yu Meinu',
            lit_translation='Wolf and the Beauty'
        )

    def test_cjk_eng_rom_ver(self):
        entry = as_node("""[[Wolf (EXO)|Lang Yu Meinu (Wolf) (EXO-M Ver.)]] (狼与美女)""")
        name = parse_generasia_track_name(entry)
        self.assertAll(
            name, 'Wolf', 'Wolf', '狼与美女', cjk='狼与美女', romanized='Lang Yu Meinu',
            extra={'version': 'EXO-M Ver.'}
        )

    def test_cjk_eng_rom(self):
        entry = as_node("""[[Growl (EXO)|Páoxiāo (Growl)]] (咆哮)""")
        name = parse_generasia_track_name(entry)
        self.assertAll(name, 'Growl', 'Growl', '咆哮', cjk='咆哮', romanized='Páoxiāo')

    def test_rom_eng_cjk_lit(self):
        entry = as_node("""[[Baby, Don't Cry|Renyu de Yanlei (Baby, Don't Cry)]] (人鱼的眼泪; ''Mermaid Tears'')""")
        name = parse_generasia_track_name(entry)
        en, cjk = 'Baby, Don\'t Cry', '人鱼的眼泪'
        self.assertAll(name, en, en, cjk, cjk=cjk, romanized='Renyu de Yanlei', lit_translation='Mermaid Tears')

    def test_rom_eng_cjk(self):
        entry = as_node("""[[Baby (EXO)|Di Yi Bu (Baby)]] (第一步)""")
        name = parse_generasia_track_name(entry)
        self.assertAll(name, 'Baby', 'Baby', '第一步', cjk='第一步', romanized='Di Yi Bu')

    def test_rom_eng_han_lit(self):
        entry = as_node("""[[Yeongwonhi Neowa Ggumgugo Shipda (Forever)]] (영원히 너와 꿈꾸고 싶다; ''I Want To Dream Forever With You'')""")
        name = parse_generasia_track_name(entry)
        rom, ko = 'Yeongwonhi Neowa Ggumgugo Shipda', '영원히 너와 꿈꾸고 싶다'
        lit = 'I Want To Dream Forever With You'
        self.assertAll(name, 'Forever', 'Forever', ko, ko, romanized=rom, lit_translation=lit)

    def test_more_rom_eng_han_lit(self):
        entry = as_node("""[[Geunyang Utja (Be Happy)]] (웃자; ''Just Smile'')""")
        name = parse_generasia_track_name(entry)
        rom, eng, ko, lit = 'Geunyang Utja', 'Be Happy', '웃자', 'Just Smile'
        self.assertAll(name, eng, eng, ko, ko, romanized=rom, lit_translation=lit)

    def test_half_enclosed_version(self):
        entry = as_node("""[[Byeol Byeol Byeol|Byeol Byeol Byeol (☆★☆)- Acoustic RnB ver.]] (별별별; ''Star Star Star'')""")
        name = parse_generasia_track_name(entry)
        rom, eng, ko, lit = 'Byeol Byeol Byeol', '☆★☆', '별별별', 'Star Star Star'
        self.assertAll(name, eng, eng, ko, ko, romanized=rom, lit_translation=lit, extra={'version': 'Acoustic R&B ver.'})

    def test_rom_eng_feat_han_lit(self):
        entry = as_node("""[[Hwaseongin Baireoseu (Boys & Girls)]] (feat. [[Key]] ([[SHINee]])) (화성인 바이러스; ''Martian Virus'')""")
        name = parse_generasia_track_name(entry)
        rom, eng, ko, lit = 'Hwaseongin Baireoseu', 'Boys & Girls', '화성인 바이러스', 'Martian Virus'
        feat = as_node("""[[Key]] ( [[SHINee]] )""")
        log.debug(f'Expected feat={feat.raw.string!r}')
        self.assertAll(name, eng, eng, ko, ko, romanized=rom, lit_translation=lit, extra={'feat': feat})

    def test_remix_feat(self):
        entry = as_node("""[[Bad Girl (Girls' Generation)|BAD GIRL (The Cataracs Remix)]] feat. [[DEV]]""", root=self.root)
        name = parse_generasia_track_name(entry)
        self.assertNamesEqual(
            name, Name('BAD GIRL', extra={'remix': 'The Cataracs Remix', 'feat': as_node("""[[DEV]]""", root=self.root)})
        )

    def test_unzipped_collabs(self):
        entry = as_node("""[[7989]] ([[Kangta]] & [[Taeyeon]] (강타&태연))""", root=self.root)
        name = parse_generasia_track_name(entry)
        expected = Name(
            '7989', extra={'artists': as_node("""( [[Kangta]] & [[Taeyeon]] (강타&태연))""", root=self.root)}
        )
        self.assertNamesEqual(name, expected)

    def test_eng_han_rom_lit_track(self):
        entry = as_node("""[[Perfect for You (Sowon)|Honey (Sowon)]] (소원; ''Wish'')""", root=self.root)
        name = parse_generasia_track_name(entry)
        self.assertNamesEqual(name, Name('Honey', '소원', romanized='Sowon', lit_translation='Wish'))


if __name__ == '__main__':
    main()
