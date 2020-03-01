#!/usr/bin/env python

import logging
import re
import sys
import unittest
from argparse import ArgumentParser
from pathlib import Path

sys.path.append(Path(__file__).parents[1].joinpath('lib').as_posix())
from ds_tools.logging import init_logging
# from music_manager.files.track.patterns import cleanup_album_name
from music_manager.files.track.parsing import AlbumName

log = logging.getLogger(__name__)
maybe_print = lambda: None


NAMES = [
    'The 2nd Mini Album `중독 (Overdose)`',
    'The 2nd Mini Album `上瘾 (Overdose)`',
    'LOVE YOURSELF 結 `Answer`',

    '언프리티 랩스타 2 Track 2',
    '화실(化-室:atelier) (Hwa:telier)',

    '인형 (Doll) - SM STATION',
    '드림웍스 트롤 X SM STATION',
    'Carpet - SM STATION',
    '그 여름 (0805)',                  # SNSD - SM STATION

    'Fallin’ Light(天使の梯子) - Single',
    'SAPPY - Single',   # Red Velvet
    'SAPPY - EP',       # Red Velvet
    'RUN‐Japanese Ver.‐【通常盤】 - Single',
    'Brand New Year Vol.2 - Single',
    'Single `Catch Me If You Can`',
    'Chocolate Love (Digital single)',

    'The Red [1st Album]',
    '#Cookie Jar [1st Japanese Mini Album]',
    '옥탑방 프로젝트 The 1st Album - 심쿵주의보',       # SNSD - Sunny

    'PIRI～笛を吹け～-Japanese ver.-',

    'SUMMER SPECIAL Pinocchio / Hot Summer',            # Title is Pinocchio / Hot Summer, it's a summer special album
    'UP&DOWN[JAPANESE VERSION]SPECIAL EDITION - EP',
    '好きと言わせたい [Type-A]',
    '好きと言わせたい [WIZ*ONE Edition]',
    'Danger (Japanese Ver.)',
    'The Best (New Edition)',       # SNSD
    'Kissing You (Rhythmer Remix Vol.1)',
    'I Feel You (CHN Ver.)',

    'Make It Right (feat. Lauv) (EDM Remix)',

    'Wannabe (Feat. San E)',

    '2019 월간 윤종신 5월호 \'별책부록\' (Monthly Project 2019 May Yoon Jong Shin with TAEYEON)',  # Taeyeon
    '임재범 30주년 기념 앨범 Project 1',     # Taeyeon
    '화양연화 (The Most Beautiful Moment in Life) pt.1',
    '[Re:flower] PROJECT #1',

    'S.M. THE BALLAD Vol.2  Breath  Set Me Free',   # SNSD
    'STARSHIP PLANET 2018(스타쉽플래닛)'
    'Wonder Best KOREA/U.S.A/JAPAN 2007-2012',
    '2001-2009 End And..',
    '4집 Super Star',
    'OH MY GIRL JAPAN DEBUT ALBUM',

    '화양연화 Young Forever',
    'Thanks Edition `바람`',
    '썸타 (Lil` Something)',
    'Puberty Book I Bom (사춘기집I 꽃기운)',
    'Ah Yeah (아예)',
    '4U Project (손만 잡을게)',
    '밤이 되니까 (因为入夜了)',

    '‘The ReVe Festival’ Day 1',
    'Re:union, The real',
    'Mabinogi (It\'s Fantastic!)',
    'O!RUL8,2?',
    'FM201.8',

    '1집 Chapter 1',     # god
    '6집 보통날',        # god

    '12시 25분 (Wish List) - Winter Garden',  # Xmas date
]

OST_NAMES = [
    '듀스 20주년 헌정앨범 Part.1',
    '인기가요 뮤직크러쉬 Part.4',
    '투유 프로젝트 - 슈가맨2 Part.3',
    '듀스 20주년 헌정앨범 Part 6',
    '연애플레이리스트4 Part.1',             # Love Playlist Season 4 Part 1
    'Fall, in girl Vol.3',

    '슬기로운 감빵생활 O.S.T Part.5',
    '추리의 여왕 시즌2 OST Part.2',
    '화랑 OST Part.2',
    '굿닥터 OST Part 3',
    '달의 연인 - 보보경심 려 OST Part 1',
    '식샤를 합시다3 : 비긴즈 OST Part.3',

    '하이드 지킬, 나 (SBS 수목드라마) OST - Part.2',
    '구르미 그린 달빛 (KBS2 월화드라마) OST - Part.9',
    '왕의 얼굴 (KBS 2TV 수목드라마) OST - Part.2',
    '닥터 이방인 Part 5 (SBS 월화 드라마)',
    '혼술남녀 (tvN 월화드라마) OST - Part.3',
    'MBC 월화 특별 기획 `야경꾼 일지` OST Part 1',
    '후아유-학교 2015 (KBS2 월화드라마) OST - Part.7',

    '어린왕자 OST',
    '스쿨오즈 - 홀로그램 뮤지컬 OST',
    '모바일 게임 \'헤븐\' OST',
    '우리 옆집에 EXO가 산다 OST',
    'Dream Knight Special OST',
    'Pokemon: The Movie XY&Z OST',
    '"개 같은 하루 (with TTG)" OST',

    'Beautiful Accident (美好的意外) OST',
    '영화 `Make Your Move` OST',

    'Hwarang OST (화랑 OST)',
    'Ruler - Master of the Mask OST (군주 - 가면의 주인 OST)',
    'Memories of the Alhambra OST (알함브라 궁전의 추억 OST)',
    
    'You Are The One - 도전에 반하다 OST PART.1',
    '디데이 OST Part.1 `아나요 (Let You Know)`',

    'The Crowned Clown OST (왕이 된 남자 OST) - Part 3',

    'Moon Lovers Scarlet Heart Ryo (달의 연인 - 보보경심 려) OST Part 3',

    'ファイナルライフ -明日、君が消えても- (Original Soundtrack)',
    'Yossism (Telemonster - Original Soundtrack)',

    'Let It Go (겨울왕국 OST 효린 버전)',

    'A Brand New Day (BTS WORLD OST Part.2)',
    'OST Best - Flash Back',
]

COMPETITION_NAMES = [
    'Queendom (퀸덤) - Fandora\'s Box - Part. 1',
    'Queendom (퀸덤) - Final Comeback Singles',
    'Queendom (퀸덤) Part. 2',
    'PRODUCE 48 - 30 Girls 6 Concepts',
    'PRODUCE 48 - 내꺼야 (PICK ME) (Piano Ver.)',
]


if __name__ == '__main__':
    parser = ArgumentParser('Album Name Parsing Unit Tests')
    parser.add_argument('--include', '-i', nargs='+', help='Names of test functions to include (default: all)')
    parser.add_argument('--verbose', '-v', action='count', default=0, help='Logging verbosity (can be specified multiple times to increase verbosity)')
    args = parser.parse_args()
    init_logging(args.verbose, log_path=None, names=None)

    for name in NAMES:
        album_name = AlbumName(name)
        if len(album_name.name_parts) > 2:
            print(f'AlbumName({name!r}) => {album_name!r}')
        # clean = cleanup_album_name(name)
        # if clean != name:
            # print(f'cleanup_album_name({name!r}) => {clean!r}')

    for name in OST_NAMES:
        album_name = AlbumName(name)
        # if album_name.network_info:
        if len(album_name.name_parts) > 2:
            print(f'OST AlbumName({name!r}) => {album_name!r}')

    # test_classes = ()
    # argv = [sys.argv[0]]
    # if args.include:
    #     names = {m: f'{cls.__name__}.{m}' for cls in test_classes for m in dir(cls)}
    #     for method_name in args.include:
    #         argv.append(names.get(method_name, method_name))

    if args.verbose:
        maybe_print = lambda: print()

    # try:
    #     unittest.main(warnings='ignore', verbosity=2, exit=False, argv=argv)
    # except KeyboardInterrupt:
    #     print()
