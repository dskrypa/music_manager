#!/usr/bin/env python

import logging
import sys
from pathlib import Path

sys.path.append(Path(__file__).parents[1].joinpath('lib').as_posix())
from music.files.track.parsing import split_artists
from music.text.name import Name
from music.test_common import NameTestCaseBase, main

log = logging.getLogger(__name__)


class FileArtistParsingTest(NameTestCaseBase):
    def assertArtistsEqual(self, parsed, expected):
        self.assertSetEqual(parsed, expected)
        for name in expected:
            artist_str = name.artist_str()
            self.assertSetEqual(set(split_artists(artist_str)), {name}, f'Failed to re-parse artist={artist_str!r}')

    def test_eng_eng_mix(self):
        names = set(split_artists('88rising, Rich Brian, 청하 (CHUNG HA)'))
        self.assertArtistsEqual(names, {Name('88rising'), Name('Rich Brian'), Name('CHUNG HA', '청하')})

    def test_zip_mix(self):
        names = set(split_artists('기희현, 전소미, 최유정, 김청하 (Heehyun (DIA), Somi, Yoo Jung, Chungha)'))
        expected = {
            Name('Heehyun', '기희현', extra={'group': Name('DIA')}), Name('Somi', '전소미'),
            Name('Yoo Jung', '최유정'), Name('Chungha', '김청하')
        }
        self.assertArtistsEqual(names, expected)

    def test_mix_2(self):
        names = set(split_artists('예성 (YESUNG), 청하 (CHUNG HA)'))
        self.assertArtistsEqual(names, {Name('YESUNG', '예성'), Name('CHUNG HA', '청하')})

    def test_mix_with_group(self):
        names = set(split_artists('지민 [Jimin (AOA)]'))
        self.assertArtistsEqual(names, {Name('Jimin', '지민', extra={'group': Name('AOA')})})

    def test_split_mix_group(self):
        names = set(split_artists('Jimin (지민) (AOA)'))
        self.assertArtistsEqual(names, {Name('Jimin', '지민', extra={'group': Name('AOA')})})

    def test_zip_ampersand(self):
        names = set(split_artists('딘딘 & 민아 (DinDin & Minah)'))
        self.assertArtistsEqual(names, {Name('DinDin', '딘딘'), Name('Minah', '민아')})

    def test_zip_x(self):
        names = set(split_artists('손동운 (하이라이트) X 서령 (공원소녀) [Son Dongwoon (Highlight) X Seoryoung (GWSN)]'))
        expected = {
            Name('Son Dongwoon', '손동운', extra={'group': Name('Highlight', '하이라이트')}),
            Name('Seoryoung', '서령', extra={'group': Name('GWSN', '공원소녀')})
        }
        self.assertArtistsEqual(names, expected)

    def test_zip_with_space(self):
        names = set(split_artists('울랄라세션 & 아이유 (Ulala Session & IU)'))
        self.assertArtistsEqual(names, {Name('Ulala Session', '울랄라세션'), Name('IU', '아이유')})

    def test_member_mix_keep_x(self):
        names = set(split_artists('주헌 (몬스타엑스) (JooHeon (MONSTA X))'))
        self.assertArtistsEqual(names, {Name('JooHeon', '주헌', extra={'group': Name('MONSTA X', '몬스타엑스')})})

    def test_member_eng_keep_x(self):
        names = set(split_artists('JooHeon (MONSTA X)'))
        self.assertArtistsEqual(names, {Name('JooHeon', extra={'group': Name('MONSTA X')})})

    def test_keep_x_mix_1(self):
        names = set(split_artists('몬스타엑스 (MONSTA X)'))
        self.assertArtistsEqual(names, {Name('MONSTA X', '몬스타엑스')})

    def test_keep_x_mix_2(self):
        names = set(split_artists('MONSTA X (몬스타엑스)'))
        self.assertArtistsEqual(names, {Name('MONSTA X', '몬스타엑스')})

    def test_keep_x(self):
        names = set(split_artists('Monsta X'))
        self.assertArtistsEqual(names, {Name('Monsta X')})

    def test_member_from_group(self):
        names = set(split_artists('G-DRAGON (from BIGBANG)'))
        self.assertArtistsEqual(names, {Name('G-DRAGON', extra={'group': Name('BIGBANG')})})

    def test_keep_parentheses_1(self):
        names = set(split_artists('f(x)'))
        self.assertArtistsEqual(names, {Name('f(x)')})

    def test_keep_parentheses_2(self):
        names = set(split_artists('(G)I-DLE ((여자)아이들)'))
        self.assertArtistsEqual(names, {Name('(G)I-DLE', '(여자)아이들')})

    def test_keep_parentheses_3(self):
        names = set(split_artists('(G)I-DLE'))
        self.assertArtistsEqual(names, {Name('(G)I-DLE')})

    def test_big_list_keep_parens(self):
        names = set(split_artists('현아 (HyunA), 조권 (Jo Kwon), 비투비 (BTOB), CLC, 펜타곤 (PENTAGON), 유선호 (Yu Seon Ho), (여자)아이들 [(G)I-DLE]'))
        expected = {
            Name('HyunA', '현아'), Name('Jo Kwon', '조권'), Name('BTOB', '비투비'), Name('CLC'),
            Name('PENTAGON', '펜타곤'), Name('Yu Seon Ho', '유선호'), Name('(G)I-DLE', '(여자)아이들')
        }
        self.assertArtistsEqual(names, expected)

    def test_no_eng(self):
        names = set(split_artists('국.슈 (국프의 핫이슈)'))
        self.assertArtistsEqual(names, {Name(non_eng='국.슈 (국프의 핫이슈)')})

    def test_unbalanced_comma(self):
        names = set(split_artists('Homme (창민, 이현)'))
        expected = {Name('Homme', extra={'members': [Name(non_eng='창민'), Name(non_eng='이현')]})}
        self.assertArtistsEqual(names, expected)

    def test_collab_group_with_members(self):
        names = set(split_artists('MOBB <MINO (from WINNER) × BOBBY (from iKON)>'))
        expected = {Name('MOBB', extra={'members': [
            Name('MINO', extra={'group': Name('WINNER')}), Name('BOBBY', extra={'group': Name('iKON')})
        ]})}
        self.assertArtistsEqual(names, expected)

    def test_no_space_mix_eng(self):
        names = set(split_artists('화사(Hwa Sa), WOOGIE'))
        self.assertArtistsEqual(names, {Name('Hwa Sa', '화사'), Name('WOOGIE')})

    def test_trailing_apostrophe(self):
        names = set(split_artists("소녀시대 (Girls' Generation), 슈퍼주니어 (Super Junior)"))
        expected = {Name("Girls' Generation", '소녀시대'), Name('Super Junior', '슈퍼주니어')}
        self.assertArtistsEqual(names, expected)

    def test_trailing_apostrophe_standalone(self):
        names = set(split_artists("소녀시대 (GIRLS' GENERATION)"))
        self.assertArtistsEqual(names, {Name("GIRLS' GENERATION", '소녀시대')})

    def test_trailing_apostrophe_standalone_alt_lang(self):
        names = set(split_artists("少女時代 (GIRLS' GENERATION)"))
        self.assertArtistsEqual(names, {Name("GIRLS' GENERATION", '少女時代')})

    def test_apostrophe_of_group(self):
        names = set(split_artists("소진 (Sojin of Girl's Day)"))
        self.assertArtistsEqual(names, {Name('Sojin', '소진', extra={'group': Name("Girl's Day")})})

    def test_mix_group_with_apostrophe_1(self):
        names = set(split_artists("민아 (걸스데이) [MinAh (Girl's Day)]"))
        self.assertArtistsEqual(names, {Name('MinAh', '민아', extra={'group': Name("Girl's Day", '걸스데이')})})

    def test_mix_group_with_apostrophe_2(self):
        names = set(split_artists("윤아 (소녀시대) [YoonA (Girls' Generation)]"))
        self.assertArtistsEqual(names, {Name('YoonA', '윤아', extra={'group': Name("Girls' Generation", '소녀시대')})})

    def test_unpaired_paren_with_group(self):
        names = set(split_artists('제아 (JeA (Brown Eyed Girls)'))
        self.assertArtistsEqual(names, {Name('JeA', '제아', extra={'group': Name('Brown Eyed Girls')})})


if __name__ == '__main__':
    main(FileArtistParsingTest)
