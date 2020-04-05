#!/usr/bin/env python

import logging
import sys
from pathlib import Path

sys.path.append(Path(__file__).parents[1].joinpath('lib').as_posix())
from music.files import split_artists
from music.text.name import Name
from music.test_common import NameTestCaseBase, main

log = logging.getLogger(__name__)

"""
TODO:
- Album: <AlbumDir('C:/Users/dougs/etc/kpop/sorting/super_junior/Girls_ Generation, Super Junior - SEOUL - Single')>
    Artists: Unexpected str list format for text="소녀시대 (Girls' Generation), 슈퍼주니어 (Super Junior)" -
processed=[]
processing=["소녀시대 (Girls' Generation)", ',', ' 슈퍼주니어 (Super Junior)']

- Album: <AlbumDir("C:/Users/dougs/etc/kpop/sorting/snsd_sort_later/GIRLS' GENERATION - Sailing - 0805 (SM STATION Single)")>
    Artists: Unexpected str list format for text="소녀시대 (GIRLS' GENERATION)" -
processed=[]
processing=["소녀시대 (GIRLS' GENERATION)"]

- Album: <AlbumDir('C:/Users/dougs/etc/kpop/sorting/snsd_members/YoonA - Deoksugung Stonewall Walkway (Feat. 10cm)')>
    Artists: Unexpected str list format for text="윤아 (소녀시대) [YoonA (Girls' Generation)]" -
processed=[]
processing=["윤아 (소녀시대) [YoonA (Girls' Generation)]"]

- Album: <AlbumDir("C:/Users/dougs/etc/kpop/sorting/snsd/GIRL'S GENERATION - The Best (New Edition)")>
    Artists: Unexpected str list format for text="少女時代 (GIRL'S GENERATION)" -
processed=[]
processing=["少女時代 (GIRL'S GENERATION)"]

- Album: <AlbumDir('C:/Users/dougs/etc/kpop/sorting/omg/Collaborations/White [with HAHA + M.TySON]')>
    Artists: Unexpected str list format for text='스컬, 타린 (' -
processed=['스컬']
processing=[' 타린 (']

- Album: <AlbumDir('C:/Users/dougs/etc/kpop/sorting/girls_day/Solo/Minah - I am a Woman too')>
    Artists: Unexpected str list format for text="민아 (걸스데이) [MinAh (Girl's Day)]" -
processed=[]
processing=["민아 (걸스데이) [MinAh (Girl's Day)]"]

- Album: <AlbumDir('C:/Users/dougs/etc/kpop/sorting/girls_day/Solo/Sojin - DEUX 20th Anniversary Tribute Album Part.1')>
    Artists: Unexpected str list format for text="소진 (Sojin of Girl's Day)" -
processed=[]
processing=["소진 (Sojin of Girl's Day)"]

- Album: <AlbumDir('C:/Users/dougs/etc/kpop/sorting/brown_eyed_girls_members/JeA (Brown Eyed Girls) - Just For One Day')>
    Artists: Unexpected str list format for text='제아 (JeA (Brown Eyed Girls)' -
processed=[]
processing=['제아 (JeA (Brown Eyed Girls)']
"""


class FileArtistParsingTest(NameTestCaseBase):
    def test_eng_eng_mix(self):
        names = set(split_artists('88rising, Rich Brian, 청하 (CHUNG HA)'))
        self.assertSetEqual(names, {Name('88rising'), Name('Rich Brian'), Name('CHUNG HA', '청하')})

    def test_zip_mix(self):
        names = set(split_artists('기희현, 전소미, 최유정, 김청하 (Heehyun (DIA), Somi, Yoo Jung, Chungha)'))
        expected = {
            Name('Heehyun (DIA)', '기희현'), Name('Somi', '전소미'), Name('Yoo Jung', '최유정'), Name('Chungha', '김청하')
        }
        self.assertSetEqual(names, expected)

    def test_mix_2(self):
        names = set(split_artists('예성 (YESUNG), 청하 (CHUNG HA)'))
        self.assertSetEqual(names, {Name('YESUNG', '예성'), Name('CHUNG HA', '청하')})

    def test_mix_with_group(self):
        names = set(split_artists('지민 [Jimin (AOA)]'))
        self.assertSetEqual(names, {Name('Jimin (AOA)', '지민')})

    def test_zip_ampersand(self):
        names = set(split_artists('딘딘 & 민아 (DinDin & Minah)'))
        self.assertSetEqual(names, {Name('DinDin', '딘딘'), Name('Minah', '민아')})

    def test_zip_x(self):
        names = set(split_artists('손동운 (하이라이트) X 서령 (공원소녀) [Son Dongwoon (Highlight) X Seoryoung (GWSN)]'))
        expected = {Name('Son Dongwoon (Highlight)', '손동운 (하이라이트)'), Name('Seoryoung (GWSN)', '서령 (공원소녀)')}
        self.assertSetEqual(names, expected)

    def test_zip_with_space(self):
        names = set(split_artists('울랄라세션 & 아이유 (Ulala Session & IU)'))
        self.assertSetEqual(names, {Name('Ulala Session', '울랄라세션'), Name('IU', '아이유')})

    def test_member_mix_keep_x(self):
        names = set(split_artists('주헌 (몬스타엑스) (JooHeon (MONSTA X))'))
        self.assertSetEqual(names, {Name('JooHeon (MONSTA X)', '주헌 (몬스타엑스)')})

    def test_member_eng_keep_x(self):
        names = set(split_artists('JooHeon (MONSTA X)'))
        self.assertSetEqual(names, {Name('JooHeon (MONSTA X)')})

    def test_keep_x_mix(self):
        names = set(split_artists('몬스타엑스 (MONSTA X)'))
        self.assertSetEqual(names, {Name('MONSTA X', '몬스타엑스')})

    def test_keep_x(self):
        names = set(split_artists('Monsta X'))
        self.assertSetEqual(names, {Name('Monsta X')})

    def test_member_from_group(self):
        names = set(split_artists('G-DRAGON (from BIGBANG)'))
        self.assertSetEqual(names, {Name('G-DRAGON', extra={'group': 'BIGBANG'})})

    def test_keep_parentheses_1(self):
        names = set(split_artists('f(x)'))
        self.assertSetEqual(names, {Name('f(x)')})

    def test_keep_parentheses_2(self):
        names = set(split_artists('(G)I-DLE ((여자)아이들)'))
        self.assertSetEqual(names, {Name('(G)I-DLE', '(여자)아이들')})

    def test_keep_parentheses_3(self):
        names = set(split_artists('(G)I-DLE'))
        self.assertSetEqual(names, {Name('(G)I-DLE')})

    def test_big_list_keep_parens(self):
        names = set(split_artists('현아 (HyunA), 조권 (Jo Kwon), 비투비 (BTOB), CLC, 펜타곤 (PENTAGON), 유선호 (Yu Seon Ho), (여자)아이들 [(G)I-DLE]'))
        expected = {
            Name('HyunA', '현아'), Name('Jo Kwon', '조권'), Name('BTOB', '비투비'), Name('CLC'),
            Name('PENTAGON', '펜타곤'), Name('Yu Seon Ho', '유선호'), Name('(G)I-DLE', '(여자)아이들')
        }
        self.assertSetEqual(names, expected)

    def test_no_eng(self):
        names = set(split_artists('국.슈 (국프의 핫이슈)'))
        self.assertSetEqual(names, {Name(None, '국.슈 (국프의 핫이슈)')})

    def test_unbalanced_comma(self):
        names = set(split_artists('Homme (창민, 이현)'))
        expected = {Name('Homme', extra={'members': [Name(None, '창민'), Name(None, '이현')]})}
        self.assertSetEqual(names, expected)

    def test_collab_group_with_members(self):
        names = set(split_artists('MOBB <MINO (from WINNER) × BOBBY (from iKON)>'))
        expected = {Name('MOBB', extra={'Members': [Name('MINO (from WINNER)'), Name('BOBBY (from iKON)')]})}
        self.assertSetEqual(names, expected)

    def test_no_space_mix_eng(self):
        names = set(split_artists('화사(Hwa Sa), WOOGIE'))
        self.assertSetEqual(names, {Name('Hwa Sa', '화사'), Name('WOOGIE')})


if __name__ == '__main__':
    main(FileArtistParsingTest)
