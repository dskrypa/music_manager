#!/usr/bin/env python

import logging
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.append(Path(__file__).parents[1].joinpath('lib').as_posix())
from wiki_nodes.nodes import as_node
from music.test_common import main, TestCaseBase
from music.text import Name
from music.wiki.parsing.utils import name_from_intro

log = logging.getLogger(__name__)


class IntroNameParsingTest(TestCaseBase):
    def test_eng_only(self):
        page = MagicMock(intro=as_node("""'''''IT'z Me''''' is the second mini album by [[ITZY]]. It was released on March 9, 2020 with "Wannabe" serving as the album's title track."""))
        names = set(name_from_intro(page))
        self.assertSetEqual(names, {Name("IT'z Me")})

    def test_with_num(self):
        page = MagicMock(intro=as_node("""'''''Map of the Soul : 7''''' is the fourth Korean full-length album by [[BTS]]. It was released on February 21, 2020 with "On" serving as the album's title track."""))
        names = set(name_from_intro(page))
        self.assertSetEqual(names, {Name('Map of the Soul: 7')})

    def test_multi_lang_versions(self):
        page = MagicMock(intro=as_node("""'''GFRIEND''' (Hangul: 여자친구; Japanese: ジーフレンド) is a six-member girl group under [[Source Music]]. They released their debut mini album ''[[Season of Glass]]'' on January 15, 2015 and held their debut stage on ''[[Music Bank
]]'' the following day.<ref>[https://www.allkpop.com/article/2015/01/album-and-mv-review-g-friend-season-of-glass Allkpop: G-Friend - ''Season of Glass'']</ref>"""))
        names = set(name_from_intro(page))
        self.assertSetEqual(names, {Name('GFRIEND', '여자친구'), Name('GFRIEND', 'ジーフレンド')})

    def test_multi_lang_with_aka(self):
        page = MagicMock(intro=as_node("""'''WJSN''' (also known as '''Cosmic Girls'''; Korean: 우주소녀, Chinese: 宇宙少女) is a thirteen-member South Korean-Chinese girl group formed by [[Starship Entertainment]] and [[Yuehua Entertainment]]. They debuted on February 25, 2
016 with their first mini album ''[[Would You Like?]]''."""))
        names = set(name_from_intro(page))
        self.assertSetEqual(names, {Name('WJSN', '우주소녀'), Name('WJSN', '宇宙少女')})


if __name__ == '__main__':
    main()
