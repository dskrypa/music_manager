#!/usr/bin/env python

from music.text.name import Name
from music.test_common import NameTestCaseBase, main


class NameMatchingTest(NameTestCaseBase):
    def test_match_multi_lang_versions(self):
        name = Name(
            'Girls\' Generation', '소녀시대', romanized='So Nyeo Si Dae', versions={
                Name('SNSD', '소녀시대', romanized='So Nyeo Si Dae'),
                Name('Girls\' Generation', '少女時代', romanized='Shoujo Jidai')
            }
        )
        self.assertTrue(name.matches('girls generation'))
        self.assertTrue(name.matches('Girls\' Generation'))
        self.assertTrue(name.matches('Girls’ Generation'))
        self.assertTrue(name.matches('소녀시대'))
        self.assertTrue(name.matches('snsd'))
        self.assertTrue(name.matches('SNSD'))
        self.assertTrue(name.matches('s.n.s.d'))
        self.assertTrue(name.matches('So Nyeo Si Dae'))
        self.assertTrue(name.matches('Shoujo Jidai'))
        self.assertTrue(name.matches('少女時代'))
        self.assertTrue(name.matches('Girls\' Generation (SNSD)'))
        self.assertTrue(name.matches('Girls\' Generation (소녀시대)'))
        self.assertTrue(name.matches('Girls\' Generation (少女時代)'))
        self.assertTrue(name.matches('少女時代(SNSD)'))
        self.assertTrue(name.matches('소녀시대(SNSD)'))
        self.assertTrue(name.matches('소녀시대(Girls\' Generation)'))

        self.assertFalse(name.matches('Girls’ Generation-Oh!GG'))
        self.assertFalse(name.matches('소녀시대-Oh!GG'))
        self.assertFalse(name.matches('sns'))

    def test_name_combination_1(self):
        a = Name('Apink', '에이핑크')
        b = Name('Apink', 'エーピンク')
        c = Name('Apink', '에이핑크', versions={b})
        self.assertNamesEqual(c + a, c)
        self.assertNamesEqual(c + b, c)

        d = Name('Apink')
        e = Name(non_eng='에이핑크')
        f = Name(non_eng='エーピンク')
        self.assertNamesEqual(d + e, a)
        self.assertNamesEqual(d + f, b)

    def test_alt_lang_name_combination(self):
        a = Name('SNSD', '소녀시대', versions={Name(non_eng='少女時代')})
        b = Name('SNSD', '少女時代', versions={Name(non_eng='소녀시대')})
        combined = a + b
        self.assertNamesEqual(combined, Name('SNSD', '소녀시대', versions=[Name('SNSD', '少女時代')]))

    def test_name_combination(self):
        a = Name('SNSD', '소녀시대', romanized='So Nyeo Si Dae')
        b = Name('SNSD')
        self.assertNamesEqual(a + b, a)

        c = Name('SNSD', romanized='So Nyeo Si Dae')
        d = Name('SNSD', '소녀시대')
        self.assertNamesEqual(c + d, a)

    def test_name_is_version(self):
        a = Name('SNSD', '소녀시대')
        b = Name('SNSD', '少女時代')
        self.assertFalse(a.is_version_of(b))
        self.assertFalse(b.is_version_of(a))
        self.assertTrue(a.is_version_of(b, True))
        self.assertTrue(b.is_version_of(a, True))

    def test_require_more_than_just_hangul(self):
        a = Name.from_enclosed('So Nyeo Si Dae (소녀시대)')
        b = Name('Heart 2 Heart with 소녀시대')
        self.assertFalse(a.matches(b))
        self.assertFalse(b.matches(a))

        c = b.split()
        self.assertFalse(a.matches(c))
        self.assertFalse(c.matches(a))

    def test_mix_replace(self):
        # a = Name('Heart 2 Heart with Girls\' Generation')
        a = Name('Heart 2 Heart with So Nyeo Si Dae')
        b = Name('Heart 2 Heart with 소녀시대')
        self.assertTrue(a.matches(b), f'\n{a.full_repr()}\n.matches is not true for\n{b.full_repr()}')
        self.assertTrue(b.matches(a), f'\n{b.full_repr()}\n.matches is not true for\n{a.full_repr()}')


if __name__ == '__main__':
    main()
