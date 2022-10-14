#!/usr/bin/env python

from unittest.mock import MagicMock

from wiki_nodes.nodes import as_node

from music.text.name import Name
from music.test_common import main, NameTestCaseBase
from music.wiki.parsing.utils import PageIntro
from music.wiki.parsing.drama_wiki import DramaWikiParser
from music.wiki.parsing.generasia import GenerasiaParser
from music.wiki.parsing.kpop_fandom import KpopFandomParser

parse_generasia_artist_name = GenerasiaParser.parse_artist_name
parse_kf_artist_name = KpopFandomParser.parse_artist_name
parse_dw_artist_name = DramaWikiParser.parse_artist_name


def fake_page(intro):
    return MagicMock(intro=lambda s: intro)


class DramaWikiArtistNameParsingTest(NameTestCaseBase):
    _site = 'wiki.d-addicts.com'

    def test_solo_artist(self):
        page = self._make_root("""==Profile==\n*'''Name:''' 조이 / Joy\n*'''Real name:''' 박수영 / Park Soo Young\n*'''Profession:''' Singer, actress\n""")
        names = set(parse_dw_artist_name(page))
        self.assertNamesEqual(names, {Name('Joy', '조이'), Name('Park Soo Young', '박수영')})

    def test_with_romanization(self):
        page = self._make_root("""==Profile==\n*'''Name:''' 김청하 / Kim Chung Ha (Gim Cheong Ha)\n*'''Real name:''' 김찬미 / Kim Chan Mi\n*'''English name:''' Annie Kim\n*'''Also known as:''' Chungha, CHUNG HA\n""")
        names = set(parse_dw_artist_name(page))
        self.assertNamesEqual(names, {Name('Kim Chung Ha', '김청하', romanized='Gim Cheong Ha'), Name('Kim Chan Mi', '김찬미')})


class GenerasiaArtistNameParsingTest(NameTestCaseBase):
    def test_solo_artist(self):
        intro = as_node("""'''BUMKEY''' (범키) is a [[K-Pop|Korean pop]]/[[K-Hip-Hop|hip-hop]] artist that debuted in 2010 under [[Brand New Music (label)|Brand New Music]]. He was a member of the [[K-Hip-Hop|hip-hop]] duo [[2winS]] and of the boy group [[TROY]]. He also participated in the special unit [[Group of 20]].""")
        names = PageIntro(fake_page(intro)).names()
        self.assertNamesEqual(names, {Name('BUMKEY', '범키')})

    def test_group_previously(self):
        intro = as_node("""'''MAMAMOO''' (마마무; previously stylized in lowercase) is a [[K-Pop|Korean pop]]/[[K-R&B|R&B]] girl group that debuted in 2014 under [[RBW Entertainment]].""")
        names = PageIntro(fake_page(intro)).names()
        self.assertNamesEqual(names, {Name('MAMAMOO', '마마무')})

    def test_multi_and(self):
        intro = as_node("""'''Girls' Generation''' (소녀시대 (''So Nyeo Si Dae'' or ''SNSD'') in Korea, and 少女時代 (''Shoujo Jidai'') in Japan) is a [[K-Pop|Korean pop]] girl group formed by [[SM Entertainment]]. Prior to their debut, they were described as the female [[Super Junior]] by [[SM Entertainment]]. They became well known after their hit 2009 song "[[Gee (song)|Gee]]". """)
        names = PageIntro(fake_page(intro)).names()
        expected = {
            Name(
                'Girls\' Generation', '소녀시대', romanized='So Nyeo Si Dae',
                versions={Name('SNSD', '소녀시대', romanized='So Nyeo Si Dae')}
            ),
            Name('Girls\' Generation', '少女時代', romanized='Shoujo Jidai'),
        }
        self.assertNamesEqual(names, expected)


class KpopFandomArtistNameParsingTest(NameTestCaseBase):
    def test_multi_non_eng(self):
        intro = as_node("""'''BTS''' (Korean: 방탄소년단; Japanese: 防弾少年团; also known as '''Bangtan Boys''' and '''Beyond the Scene''') is a seven-member boy group under [[Big Hit Entertainment]]. They debuted on June 13, 2013 with their first single ''[[2 Cool 4 Skool]]''.""")
        names = PageIntro(fake_page(intro)).names()
        self.assertNamesEqual(names, {Name('BTS', '방탄소년단'), Name('BTS', '防弾少年团')})

    def test_name_with_space(self):
        intro = as_node("""'''Red Velvet''' (레드벨벳) is a five-member girl group under [[SM Entertainment]]. They debuted as four on August 1, 2014 with the single "[[Happiness]]". [[Yeri (Red Velvet)|Yeri]] was added on the group in March 2015.""")
        names = PageIntro(fake_page(intro)).names()
        self.assertNamesEqual(names, {Name('Red Velvet', '레드벨벳')})

    def test_name_with_stylized(self):
        intro = as_node("""'''BLACKPINK''' (블랙핑크; stylized as '''BLΛƆKPIИK''') is a four-member girl group under [[YG Entertainment]]. They debuted on August 8, 2016 with their digital single album "[[Square One]]".""")
        names = PageIntro(fake_page(intro)).names()
        self.assertNamesEqual(names, {Name('BLACKPINK', '블랙핑크')})

    def test_name_with_parens(self):
        intro = as_node("""'''(G)I-DLE''' ((여자)아이들) is a six-member girl group under [[Cube Entertainment]]. They debuted on May 2, 2018 with their first mini album ''[[I Am ((G)I-DLE)|I Am]]''.""")
        names = PageIntro(fake_page(intro)).names()
        self.assertNamesEqual(names, {Name('(G)I-DLE', '(여자)아이들')})

    def test_solo_artist(self):
        intro = as_node("""'''Taeyeon''' (태연) is a South Korean singer under [[SM Entertainment]]. She is the leader of the girl group [[Girls' Generation]] and a member of its sub-units [[Girls' Generation-TTS]] and [[Girls' Generation-Oh!GG]].""")
        names = PageIntro(fake_page(intro)).names()
        self.assertNamesEqual(names, {Name('Taeyeon', '태연')})

    def test_comma_in_parens(self):
        intro = as_node("""'''OH MY GIRL''' (오마이걸, also stylized as OMG) is a seven-member girl group under [[WM Entertainment]]. They debuted on April 21, 2015 with the song "Cupid" from their first [[Oh My Girl (album)|self-titled mini album]].""")
        names = PageIntro(fake_page(intro)).names()
        self.assertNamesEqual(names, {Name('OH MY GIRL', '오마이걸')})

    def test_no_non_eng(self):
        intro = as_node("""'''RM''' (short for Real Me<ref>[https://www.etonline.com/bts-answers-fans-biggest-burning-questions-and-rm-reveals-why-he-changed-his-name-rap-monster-91173 BTS Answers Fans' Biggest Burning Questions – And RM Reveals Why He Changed His Name From Rap Monster!]</ref>, formerly '''Rap Monster''') is a South Korean rapper-songwriter, composer and producer under [[Big Hit Entertainment]]. He is the leader and main rapper of the boy group [[BTS]].""")
        names = PageIntro(fake_page(intro)).names()
        self.assertNamesEqual(names, {Name('RM')})


if __name__ == '__main__':
    main()
