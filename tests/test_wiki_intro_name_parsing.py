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


if __name__ == '__main__':
    main()
