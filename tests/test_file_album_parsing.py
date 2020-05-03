#!/usr/bin/env python

import logging
import sys
from pathlib import Path

from ds_tools.test_common import main, TestCaseBase

sys.path.append(Path(__file__).parents[1].joinpath('lib').as_posix())
# from music_manager.files.track.patterns import cleanup_album_name
from music.files.track.parsing import AlbumName
from music.text.name import Name, sort_name_parts

log = logging.getLogger(__name__)

ALBUM_TEST_CASES = {
    'OBSESSION - The 6th Album': AlbumName('OBSESSION', alb_num='6th Album', alb_type='Album'),
    'The 2nd Mini Album `중독 (Overdose)`': AlbumName(('중독', 'Overdose'), alb_num='2nd Mini Album', alb_type='Mini Album'),
    'The 2nd Mini Album `上瘾 (Overdose)`': AlbumName(('上瘾', 'Overdose'), alb_num='2nd Mini Album', alb_type='Mini Album'),

    '인형 (Doll) - SM STATION': AlbumName(('인형', 'Doll'), sm_station=True),
    '드림웍스 트롤 X SM STATION': AlbumName('드림웍스 트롤', sm_station=True),
    'Carpet - SM STATION': AlbumName('Carpet', sm_station=True),
    '그 여름 (0805)': AlbumName(('그 여름', '0805')),             # SNSD - SM STATION

    'Fallin’ Light(天使の梯子) - Single': AlbumName(("Fallin' Light", '天使の梯子'), alb_type='Single'),
    'SAPPY - Single': AlbumName('SAPPY', alb_type='Single'),
    'SAPPY - EP': AlbumName('SAPPY', alb_type='EP'),
    'RUN‐Japanese Ver.‐【通常盤】 - Single': AlbumName(('RUN', '通常盤'), alb_type='Single', version='Japanese Ver.'),
    'Brand New Year Vol.2 - Single': AlbumName('Brand New Year Vol.2', alb_type='Single'),
    'Single `Catch Me If You Can`': AlbumName('Catch Me If You Can', alb_type='Single'),
    'Chocolate Love (Digital single)': AlbumName('Chocolate Love', alb_type='Digital single'),

    'The Red [1st Album]': AlbumName('The Red', alb_num='1st Album', alb_type='Album'),
    '#Cookie Jar [1st Japanese Mini Album]': AlbumName('#Cookie Jar', alb_num='1st Japanese Mini Album', alb_type='Japanese Mini Album'),
    'PIRI～笛を吹け～-Japanese ver.-': AlbumName(('PIRI', '笛を吹け'), version='Japanese ver.'),
    'SUMMER SPECIAL Pinocchio / Hot Summer': AlbumName('Pinocchio / Hot Summer', alb_type='SUMMER SPECIAL'),
    'UP&DOWN[JAPANESE VERSION]SPECIAL EDITION - EP': AlbumName('UP&DOWN', alb_type='EP', edition='SPECIAL EDITION', version='JAPANESE VERSION'),
    '好きと言わせたい [Type-A]': AlbumName(('好きと言わせたい', 'Type-A')),
    '好きと言わせたい [WIZ*ONE Edition]': AlbumName('好きと言わせたい', edition='WIZ*ONE Edition'),
    'Danger (Japanese Ver.)': AlbumName('Danger', version='Japanese Ver.'),
    'The Best (New Edition)': AlbumName('The Best', edition='New Edition'),
    'Kissing You (Rhythmer Remix Vol.1)': AlbumName('Kissing You', remix='Rhythmer Remix Vol.1'),
    'I Feel You (CHN Ver.)': AlbumName('I Feel You', version='CHN Ver.'),

    'Make It Right (feat. Lauv) (EDM Remix)': AlbumName('Make It Right', feat=(Name('Lauv'),), remix='EDM Remix'),
    'Wannabe (Feat. San E)': AlbumName('Wannabe', feat=(Name('San E'),)),

    "2019 월간 윤종신 5월호 '별책부록' (Monthly Project 2019 May Yoon Jong Shin with TAEYEON)": AlbumName(('2019 월간 윤종신 5월호', '별책부록', 'Monthly Project 2019 May Yoon Jong Shin with TAEYEON')),
    '임재범 30주년 기념 앨범 Project 1': AlbumName('임재범 30주년 기념 앨범 Project 1'),

    '[Re:flower] PROJECT #1': AlbumName(('Re:flower', 'PROJECT #1')),
    '2001-2009 End And..': AlbumName('2001-2009 End And..'),
    '4집 Super Star': AlbumName('4집 Super Star'),
    'OH MY GIRL JAPAN DEBUT ALBUM': AlbumName('OH MY GIRL JAPAN DEBUT ALBUM'),

    '화양연화 Young Forever': AlbumName('화양연화 Young Forever'),
    'Thanks Edition `바람`': AlbumName('바람', edition='Thanks Edition'),
    '썸타 (Lil` Something)': AlbumName(('썸타', "Lil' Something")),
    'Puberty Book I Bom (사춘기집I 꽃기운)': AlbumName(('Puberty Book I Bom', '사춘기집I 꽃기운')),
    'Ah Yeah (아예)': AlbumName(('Ah Yeah', '아예')),
    '4U Project (손만 잡을게)': AlbumName(('4U Project', '손만 잡을게')),
    '밤이 되니까 (因为入夜了)': AlbumName(('밤이 되니까', '因为入夜了')),

    'Re:union, The real': AlbumName('Re:union, The real'),
    "Mabinogi (It's Fantastic!)": AlbumName(('Mabinogi', "It's Fantastic!")),
    'O!RUL8,2?': AlbumName('O!RUL8,2?'),
    'FM201.8': AlbumName('FM201.8'),

    'Fall, in girl Vol.3': AlbumName('Fall, in girl Vol.3'),
    '1집 Chapter 1': AlbumName('1집 Chapter 1'),  # g.o.d
    '6집 보통날': AlbumName('6집 보통날'),          # g.o.d
    '12시 25분 (Wish List) - Winter Garden': AlbumName(('12시 25분', 'Wish List', 'Winter Garden')),    # xmas date

    '‘The ReVe Festival’ Day 1': AlbumName("'The ReVe Festival' Day 1"),
    "‘The ReVe Festival’ Finale": AlbumName("'The ReVe Festival' Finale"),

    '솔직히 지친다.newwav': AlbumName(
        Name(non_eng='솔직히 지친다', versions=[Name.from_enclosed('솔직히 지친다.newwav')])
    ),
    ('위키미키(Weki Meki) Digital Single [DAZZLE DAZZLE]', '위키미키 (Weki Meki)'): AlbumName(
        'DAZZLE DAZZLE', alb_type='Digital Single'
    ),
    ('The 1st Mini Album', '슈퍼엠 (SuperM)'): AlbumName(None, alb_num='1st Mini Album', alb_type='Mini Album'),
    ('Let\'s Go Everywhere - Korean Air X SuperM', 'SuperM'): AlbumName(
        'Let\'s Go Everywhere', collabs=(Name('Korean Air'),)
    ),
}

UNCOMMON_TEST_CASES = {
    # 'LOVE YOURSELF 結 `Answer`': AlbumName('LOVE YOURSELF 結 \'Answer\''),
    # '언프리티 랩스타 2 Track 2': AlbumName('언프리티 랩스타 2 Track 2'),
    # '화실(化-室:atelier) (Hwa:telier)': AlbumName(('화실', '化-室:atelier', 'Hwa:telier')),
    # '옥탑방 프로젝트 The 1st Album - 심쿵주의보': AlbumName(('옥탑방 프로젝트', '심쿵주의보'), alb_num='1st Album'),
    # '화양연화 (The Most Beautiful Moment in Life) pt.1': AlbumName(('화양연화', 'The Most Beautiful Moment in Life', 'pt.1')),
    # 'S.M. THE BALLAD Vol.2  Breath  Set Me Free': AlbumName('S.M. THE BALLAD Vol.2  Breath  Set Me Free'),    # SNSD
    # 'STARSHIP PLANET 2018(스타쉽플래닛)Wonder Best KOREA/U.S.A/JAPAN 2007-2012': AlbumName(('STARSHIP PLANET 2018', '스타쉽플래닛', 'Wonder Best KOREA/U.S.A/JAPAN 2007-2012')),
}

OST_TEST_CASES = {
    '듀스 20주년 헌정앨범 Part.1': AlbumName('듀스 20주년 헌정앨범', ost=True, part=1),
    '인기가요 뮤직크러쉬 Part.4': AlbumName('인기가요 뮤직크러쉬', ost=True, part=4),
    '투유 프로젝트 - 슈가맨2 Part.3': AlbumName('투유 프로젝트 - 슈가맨2', ost=True, part=3),
    '듀스 20주년 헌정앨범 Part 6': AlbumName('듀스 20주년 헌정앨범', ost=True, part=6),
    '연애플레이리스트4 Part.1': AlbumName('연애플레이리스트4', ost=True, part=1),

    '슬기로운 감빵생활 O.S.T Part.5': AlbumName('슬기로운 감빵생활', ost=True, part=5),
    '추리의 여왕 시즌2 OST Part.2': AlbumName('추리의 여왕 시즌2', ost=True, part=2),
    '화랑 OST Part.2': AlbumName('화랑', ost=True, part=2),
    '굿닥터 OST Part 3': AlbumName('굿닥터', ost=True, part=3),
    '달의 연인 - 보보경심 려 OST Part 1': AlbumName('달의 연인 - 보보경심 려', ost=True, part=1),
    '식샤를 합시다3 : 비긴즈 OST Part.3': AlbumName('식샤를 합시다3 : 비긴즈', ost=True, part=3),

    '하이드 지킬, 나 (SBS 수목드라마) OST - Part.2': AlbumName('하이드 지킬, 나', network_info='SBS 수목드라마', ost=True, part=2),
    '구르미 그린 달빛 (KBS2 월화드라마) OST - Part.9': AlbumName('구르미 그린 달빛', network_info='KBS2 월화드라마', ost=True, part=9),
    '왕의 얼굴 (KBS 2TV 수목드라마) OST - Part.2': AlbumName('왕의 얼굴', network_info='KBS 2TV 수목드라마', ost=True, part=2),
    '혼술남녀 (tvN 월화드라마) OST - Part.3': AlbumName('혼술남녀', network_info='tvN 월화드라마', ost=True, part=3),
    'MBC 월화 특별 기획 `야경꾼 일지` OST Part 1': AlbumName('야경꾼 일지', network_info='MBC 월화 특별 기획', ost=True, part=1),
    '후아유-학교 2015 (KBS2 월화드라마) OST - Part.7': AlbumName('후아유-학교 2015', network_info='KBS2 월화드라마', ost=True, part=7),
    '닥터 이방인 Part 5 (SBS 월화 드라마)': AlbumName('닥터 이방인', network_info='SBS 월화 드라마', ost=True, part=5),

    '어린왕자 OST': AlbumName('어린왕자', ost=True),
    '스쿨오즈 - 홀로그램 뮤지컬 OST': AlbumName('스쿨오즈 - 홀로그램 뮤지컬', ost=True),
    "모바일 게임 '헤븐' OST": AlbumName(('모바일 게임', '헤븐'), ost=True),
    '우리 옆집에 EXO가 산다 OST': AlbumName('우리 옆집에 EXO가 산다', ost=True),
    'Dream Knight Special OST': AlbumName('Dream Knight Special', ost=True),
    'Pokemon: The Movie XY&Z OST': AlbumName('Pokemon: The Movie XY&Z', ost=True),
    'Yossism (Telemonster - Original Soundtrack)': AlbumName('Telemonster', ost=True, song_name=Name('Yossism')),

    'Beautiful Accident (美好的意外) OST': AlbumName(('Beautiful Accident', '美好的意外'), ost=True),
    '영화 `Make Your Move` OST': AlbumName('Make Your Move', ost=True),
    'Hwarang OST (화랑 OST)': AlbumName(('Hwarang', '화랑'), ost=True),
    'Ruler - Master of the Mask OST (군주 - 가면의 주인 OST)': AlbumName(('Ruler - Master of the Mask', '군주 - 가면의 주인'), ost=True),
    'Memories of the Alhambra OST (알함브라 궁전의 추억 OST)': AlbumName(('Memories of the Alhambra', '알함브라 궁전의 추억'), ost=True),
    'You Are The One - 도전에 반하다 OST PART.1': AlbumName(('You Are The One', '도전에 반하다'), ost=True, part=1),
    '디데이 OST Part.1 `아나요 (Let You Know)`': AlbumName('디데이', ost=True, song_name=Name('Let You Know', '아나요'), part=1),
    'The Crowned Clown OST (왕이 된 남자 OST) - Part 3': AlbumName(('The Crowned Clown', '왕이 된 남자'), ost=True, part=3),
    'Moon Lovers Scarlet Heart Ryo (달의 연인 - 보보경심 려) OST Part 3': AlbumName(('Moon Lovers Scarlet Heart Ryo', '달의 연인 - 보보경심 려'), ost=True, part=3),
    'ファイナルライフ -明日、君が消えても- (Original Soundtrack)': AlbumName(('ファイナルライフ', '明日、君が消えても'), ost=True),
    'Let It Go (겨울왕국 OST 효린 버전)': AlbumName('겨울왕국', ost=True, song_name=Name('Let It Go'), version='효린 버전'),
    'A Brand New Day (BTS WORLD OST Part.2)': AlbumName('BTS WORLD', ost=True, song_name=Name('A Brand New Day'), part=2),
    'OST Best - Flash Back': AlbumName('OST Best - Flash Back'),
    '"개 같은 하루 (with TTG)" OST': AlbumName('개 같은 하루', ost=True, feat=(Name('TTG'),)),
}

# OST_EDGE_CASES = {
# }

# COMPETITION_TEST_CASES = {
#     "Queendom (퀸덤) - Fandora's Box - Part. 1": AlbumName(('Queendom', '퀸덤', "Fandora's Box"), ost=True, part=1),
#     'Queendom (퀸덤) - Final Comeback Singles': AlbumName(('Queendom', '퀸덤', 'Final Comeback Singles')),
#     'Queendom (퀸덤) Part. 2': AlbumName(('Queendom', '퀸덤'), ost=True, part=2),
#     'PRODUCE 48 - 30 Girls 6 Concepts': AlbumName('PRODUCE 48 - 30 Girls 6 Concepts'),
#     'PRODUCE 48 - 내꺼야 (PICK ME) (Piano Ver.)': AlbumName(('PRODUCE 48 - 내꺼야', 'PICK ME'), version='Piano Ver.'),
# }


class FileAlbumParsingTestCase(TestCaseBase):
    def test_non_osts(self):
        self._test_cases(ALBUM_TEST_CASES)

    def test_osts(self):
        self._test_cases(OST_TEST_CASES)

    # def test_ost_edge_cases(self):
    #     self._test_cases(OST_EDGE_CASES)

    def _test_cases(self, cases):
        total = len(cases)
        passed = 0
        for test_case, expected in cases.items():
            log.log(19, '')
            if isinstance(test_case, tuple):
                parsed = AlbumName.parse(*test_case)
            else:
                parsed = AlbumName.parse(test_case)
            if parsed == expected:
                passed += 1
            else:
                log.error(f'AlbumName.parse({test_case!r}) =>\n  parsed={parsed}\n!=\n{expected=}', extra={'color': 13})

        msg = f'{passed}/{total} ({passed/total:.2%}) of test cases passed'
        log.info(msg)
        self.assertEqual(passed, total)

    def test_lang_sort_order(self):
        cases = [
            (('a', '한'), ('a', '한')),
            (('한', 'a'), ('a', '한')),
            (('z한', 'a한'), ('z한', 'a한')),
            (('z한', 'a'), ('a', 'z한')),
        ]
        for case, expected in cases:
            self.assertSequenceEqual(sort_name_parts(case), expected)


if __name__ == '__main__':
    main()
