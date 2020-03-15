#!/usr/bin/env python

import logging
import sys
from pathlib import Path

sys.path.append(Path(__file__).parents[1].joinpath('lib').as_posix())
from wiki_nodes.nodes import as_node
from music.wiki.parsing.generasia import GenerasiaParser
from music.test_common import NameTestCaseBase, main

log = logging.getLogger(__name__)

parse_generasia_track_name = GenerasiaParser.parse_track_name


class GenerasiaTrackNameParsingTest(NameTestCaseBase):
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

    def test_rom_han_eng_with_feat(self):
        entry = as_node("""[[Selfish (Moonbyul)|SELFISH]] (feat. [[Seulgi]] of [[Red Velvet]])""")
        name = parse_generasia_track_name(entry)
        self.assertAll(name, 'SELFISH', 'SELFISH', extra={'feat': ...})

    def test_rom_inst(self):
        entry = as_node("""[[Neona Hae|Neona Hae (Inst.)]]""")
        name = parse_generasia_track_name(entry)
        self.assertAll(name, romanized='Neona Hae', extra='Inst.')


if __name__ == '__main__':
    main(GenerasiaTrackNameParsingTest)
