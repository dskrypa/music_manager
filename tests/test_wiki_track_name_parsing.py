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


if __name__ == '__main__':
    main(GenerasiaTrackNameParsingTest)
