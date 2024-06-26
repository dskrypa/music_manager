"""
:author: Doug Skrypa
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, InitVar, fields
from functools import cached_property, reduce
from operator import xor
from typing import Iterator, Sequence, Collection, Union, MutableSequence, Optional, Iterable, Pattern

from ds_tools.unicode.languages import LangCat
from ds_tools.unicode.hangul.constants import HANGUL_REGEX_CHAR_CLASS
from ..common.disco_entry import DiscoEntryType
from ..text.extraction import split_enclosed, has_unpaired, ends_with_enclosed, get_unpaired, strip_unpaired
from ..text.name import Name, sort_name_parts
from ..text.utils import find_ordinal, NumberParser, parse_int_words

__all__ = ['AlbumName', 'split_artists', 'UnexpectedListFormat']
log = logging.getLogger(__name__)

ATTR_NAMES = {'alb_type': 'type', 'sm_station': 'SM', 'version': 'ver', 'alb_num': 'num', 'ost': 'OST'}
APOSTROPHES = "'`՚՛՜՝‘’"
CHANNELS = ('sbs', 'kbs', 'tvn', 'mbc')

ALB_TYPE_DASH_SUFFIX_MATCH = re.compile(r'(.*)\s[-X]\s*((?:EP|Single|SM[\s-]?STATION))$', re.IGNORECASE).match
CHANNEL_PREFIX_MATCH = re.compile(
    r'^((?:{})\d*)\s+([{}\s]+)$'.format('|'.join(CHANNELS), HANGUL_REGEX_CHAR_CLASS[1:-1]), re.IGNORECASE
).match
NTH_ALB_TYPE_MATCH = re.compile(
    r'^(.*?)(?:the)?\s*((?:(?:japan|china?)(?:ese)?|korean?)?\s*[0-9]+(?:st|nd|rd|th))\s+'
    r'(.*?album\s*(?:repackage)?)(.*)$',
    re.IGNORECASE,
).match
OST_PART_MATCH = re.compile(
    '(.*?)'
    + r'\s((?:O\.?S\.?T\.?)?)\s*[:-]?\s*((?:Part|Code No)?)\.?\s*'
    + r'(\d+|' + '|'.join(NumberParser.word_value_map) + ')'
    + '$',
    re.IGNORECASE,
).match
REPACKAGE_ALBUM_MATCH = re.compile(r'^re:?package\salbum\s(.*)$', re.IGNORECASE).match
SPECIAL_PREFIX_MATCH = re.compile(r'^(\S+\s+special)\s+(.*)$', re.IGNORECASE).match


@dataclass
class AlbumName:
    name_parts: InitVar[Union[str, Iterable[str], Name, None]]
    alb_type: str = None
    alb_num: str = None
    sm_station: bool = False
    edition: str = None
    remix: str = None
    version: str = None
    ost: bool = False
    repackage: bool = False
    remastered: bool = False
    part: int = None
    network_info: str = None
    part_name: str = None
    feat: tuple[Name, ...] = None
    collabs: tuple[Name, ...] = None
    song_name: Name = None
    name: Name = None

    def __post_init__(self, name_parts):
        if name_parts is None:
            self.name = Name()
        elif isinstance(name_parts, Name):
            self.name = name_parts
        else:
            if isinstance(name_parts, str):
                name_parts = (name_parts,)
            self.name = Name(*sort_name_parts(name_parts))

    def __repr__(self) -> str:
        parts = ', '.join(sorted(f'{k}={v!r}' for k, v in zip(_fields(self), self.__parts) if v and k != 'name'))
        parts = f', {parts}' if parts else ''
        return f'{self.__class__.__name__}[{self.type.name}]({self.name!r}{parts})'

    def __dir__(self) -> list[str]:
        return sorted(set(dir(self.__class__)).union(_fields(self)))

    @cached_property
    def __parts(self):
        return tuple(getattr(self, attr) for attr in _fields(self))

    def __hash__(self) -> int:
        return hash(self.__class__) ^ reduce(xor, map(hash, self.__parts))

    def __eq__(self, other) -> bool:
        if not isinstance(other, self.__class__):
            return False
        return self.__parts == other.__parts

    def __lt__(self, other) -> bool:
        if not isinstance(other, self.__class__):
            return NotImplemented
        return self.name < other.name

    @cached_property
    def type(self) -> DiscoEntryType:
        if self.ost:
            return DiscoEntryType.Soundtrack
        if alb_type := self.alb_type:
            try:
                return DiscoEntryType.for_name(alb_type)
            except Exception as e:
                log.debug(f'Error determining DiscoEntryType for {alb_type=}: {e}')
        return DiscoEntryType.UNKNOWN

    @cached_property
    def number(self) -> Optional[int]:
        if alb_num := self.alb_num:
            return find_ordinal(alb_num)
        return None

    @classmethod
    def parse(cls, name: str, artist: str = None) -> AlbumName:
        self = cls.__new__(cls)                                         # type: AlbumName
        artist = Name.from_enclosed(artist) if artist else None         # type: Optional[Name]

        if 'repackage' in name.lower():
            self.repackage = True

        if m := ALB_TYPE_DASH_SUFFIX_MATCH(name):
            name, alb_type = map(clean, m.groups())
            if 'station' in alb_type.lower():
                self.sm_station = True
            else:
                self.alb_type = alb_type

        if name.endswith(' OST'):
            name = clean(name[:-4])
            self.ost = True
        elif m := OST_PART_MATCH(name):
            _name, _ost, _part, part_num = map(clean, m.groups())
            if _part or _ost:
                self.ost = True
                self.part = parse_int_words(part_num)
                name = _name

        try:
            parts = list(filter(None, map(clean, reversed(split_enclosed(name, reverse=True)))))
        except ValueError:
            name_parts = (fix_apostrophes(name),)
            versions = []
            real_album = None
        else:
            name_parts, real_album, versions = self._process_name_parts(parts, artist, name)

        if real_album:
            if name_parts:
                self.song_name = Name(*sort_name_parts(split_name(tuple(reversed(name_parts)))))
            name_parts = (real_album,)
        else:
            name_parts = split_name(tuple(reversed(name_parts)))

        self.name = Name(*sort_name_parts(name_parts))
        if versions:
            self.name.update(versions=set(versions))
        return self

    def _process_name_parts(self, parts, artist, name):
        real_album = None
        feat = []
        collabs = []
        versions = []
        orig_parts = parts.copy()
        name_parts = []
        i = -1
        while parts:
            i += 1
            part = fix_apostrophes(parts.pop(0))
            lc_part = part.lower()
            # log.debug(f'Processing part={part!r} / lc_part={lc_part!r}')
            if self._process_simple(part, lc_part):
                pass
            elif ost_result := self._process_ost_match(part, lc_part, orig_parts, i, name_parts):
                if ost_result is not True:
                    real_album = ost_result
            elif self._process_album_type_version(part, parts, name_parts, versions, orig_parts):
                pass
            elif self._process_artist_collabs(part, lc_part, name_parts, artist, name, orig_parts, collabs, feat):
                pass
            else:
                # log.debug(f'No cases matched {part=}')
                name_parts.append(part)

        if len(name_parts) == 2 and _langs_match(name_parts) and sum(1 for c in APOSTROPHES if c in name) == 2:
            name_parts = [f'\'{name_parts[1]}\' {name_parts[0]}']  # reversed above

        if feat:
            self.feat = tuple(feat)
        if collabs:
            self.collabs = tuple(collabs)

        # log.debug(f'Returning {name_parts=} {real_album=} {versions=}')
        return name_parts, real_album, versions

    def _process_simple(self, part, lc_part) -> bool:
        if self.ost and part == '영화':  # movie
            pass
        elif lc_part == 'repackage':
            self.repackage = True
        elif lc_part == 'remastered':
            self.remastered = True
        elif 'edition' in lc_part:
            self.edition = part
        elif 'remix' in lc_part:
            self.remix = part
        elif lc_part.endswith('single'):
            self.alb_type = part
        else:
            return False
        return True

    def _process_album_type_version(self, part, parts, name_parts, versions, orig_parts) -> bool:
        if m := NTH_ALB_TYPE_MATCH(part):
            # log.debug(f'Found NTH_ALB_TYPE_MATCH({part!r}) => {m.groups()}')
            before, num, alb_type, after = map(str.strip, m.groups())
            self.alb_num = f'{num} {alb_type}'
            self.alb_type = alb_type
            for part in (after, before):
                if part.endswith('-'):
                    part = part[:-1].strip()
                if part:
                    # log.debug(f'Re-inserting {part=}')
                    parts.insert(0, part)
        elif m := REPACKAGE_ALBUM_MATCH(part):
            self.repackage = True
            self.alb_type = 'Album'
            part = m.group(1).strip()
            if part:
                # log.debug(f'Re-inserting {part=}')
                parts.insert(0, part)
        elif m := SPECIAL_PREFIX_MATCH(part):
            self.alb_type, part = map(clean, m.groups())
            if part:
                name_parts.append(part)
        elif len(orig_parts) == 1 and LangCat.categorize(part) == LangCat.MIX and '.' in part:
            versions.append(Name.from_enclosed(part))
            name_parts.append(part.split('.')[0])
        else:
            return False
        return True

    def _process_ost_match(self, part, lc_part, orig_parts, i, name_parts) -> Union[str, bool]:
        # log.debug(f'Processing for OST matches: {i=} {part=} {lc_part=}')
        real_album = None
        if any(lc_part.endswith(val) for val in (' version', ' ver.', ' ver', ' 버전')):
            try:
                if ost_idx := lc_part.index(' ost '):
                    self.ost = True
                    real_album = clean(part[:ost_idx])
                    self.version = clean(part[ost_idx + 5:])
                else:
                    self.version = part
            except ValueError:
                self.version = part
        elif m := CHANNEL_PREFIX_MATCH(part):
            # log.debug(f'CHANNEL_PREFIX_MATCH({part}) => {m.groups()}')
            if lc_part.endswith('드라마') or '특별' in lc_part:
                self.network_info = part
            else:
                self.network_info, remainder = m.groups()
                name_parts.append(remainder)
        elif lc_part.startswith(CHANNELS) and (lc_part.endswith('드라마') or '특별' in lc_part):
            self.network_info = part  # This catches some cases that the above check does not
        elif suffix := next((s for s in ('original soundtrack', ' ost') if lc_part.endswith(s)), None):
            # log.debug(f'Found OST suffix in {lc_part=}')
            part = clean(part[:-len(suffix)])
            self.ost = True
            if len(orig_parts) == 2 and 'OST' not in orig_parts[int(not i)]:
                real_album = part
                part = None
            if part:
                name_parts.append(part)
        elif m := OST_PART_MATCH(part):
            # log.debug(f'OST_PART_MATCH({part!r}) => {m.groups()} [{orig_parts=}]')
            _part, _ost, _part_, part_num = map(clean, m.groups())
            if _part_ or _ost:
                self.ost = True
                self.part = parse_int_words(part_num)
                part = _part
                if len(orig_parts) == 2 and 'OST' not in orig_parts[int(not i)]:
                    real_album = part
                    part = None

            if part:
                name_parts.append(part)
        elif self.ost and part.startswith('드라마 '):  # "drama"
            name_parts.append(part.split(maxsplit=1)[-1].strip())
        else:
            return False
        return real_album or True

    def _process_artist_collabs(self, part, lc_part, name_parts, artist, name, orig_parts, collabs, feat) -> bool:
        if lc_part.startswith(('feat', 'with ')):
            try:
                feat_artist = part.split(maxsplit=1)[1]
            except IndexError:
                name_parts.append(part)
            else:
                feat.extend(split_artists(feat_artist))
        elif name_parts and artist and artist.matches(part):
            if len(name_parts) == 1 and name.endswith(f'~{name_parts[0]}~'):
                name_parts[0] = f'{strip_unpaired(part)} ~{name_parts[0]}~'
            else:
                log.debug(f'Discarding album name {part=} that matches {artist=}')
        elif artist and artist.english and len(orig_parts) == 1 and ' - ' in part and artist.english in part:
            _parts = tuple(map(str.strip, part.split(' - ', 1)))
            ni, ai = (1, 0) if artist.english in _parts[0] else (0, 1)
            name_parts.append(_parts[ni])
            collab_part = _parts[ai]
            if not collab_part.lower().endswith('repackage'):
                collabs.extend(n for n in split_artists(collab_part) if not artist.matches(n))
        else:
            return False
        return True


def _fields(obj):
    for field in fields(obj):
        yield field.name


def split_name(name_parts):
    if len(name_parts) == 1:
        name = name_parts[0]
        if LangCat.categorize(name) == LangCat.MIX:
            name_parts = split_enclosed(name)
            if len(name_parts) == 1 and ' - ' in name:
                name_parts = tuple(map(clean, name.split(' - ')))
    elif len(name_parts) == 2 and all(LangCat.categorize(p) == LangCat.ENG for p in name_parts):
        name_parts = ['{} ({})'.format(*name_parts)]

    return name_parts


def clean(text):
    return text.strip(' -"')


def fix_apostrophes(text: str) -> str:
    try:
        table = fix_apostrophes._table
    except AttributeError:
        table = fix_apostrophes._table = str.maketrans({c: "'" for c in APOSTROPHES})
    return text.translate(table)


class _ArtistSplitter:
    def split_artists(self, text: str) -> list[Name]:
        try:
            return self._split_artists(text)
        except UnexpectedListFormat:
            if ends_with_enclosed(text) and get_unpaired(text) == '(':
                return self._split_artists(text + ')')
            raise

    def _split_artists(self, text: str) -> list[Name]:
        if pairs := self._unzipped_list_pairs(text):
            return [self._artist_name(pair) for pair in pairs]
        else:
            return [self._artist_name(part) for part in self.split_str_list(text)]

    # region Artist Name

    def _artist_name(self, part: str | Sequence[str]) -> Name:
        parts = split_enclosed(part, True, maxsplit=1) if isinstance(part, str) else part
        if len(parts) != 2:
            return self._default_artist_name(part, parts)
        elif self._contains_delim(parts[1]):
            # log.debug(f'Split group/members {parts=}')
            return Name.from_enclosed(parts[0], extra={'members': split_artists(parts[1])})
        elif parts[1].startswith(('from ', 'of ')):
            # log.debug(f'Split soloist/group {parts=}')
            return Name.from_enclosed(parts[0], extra={'group': Name.from_enclosed(parts[1].split(maxsplit=1)[1])})
        elif all(ends_with_enclosed(p) for p in parts):
            if all(LangCat.categorize(p) == LangCat.MIX for p in parts):
                artist_a, artist_b = split_enclosed(parts[0], True, maxsplit=1)
                group_a, group_b = split_enclosed(parts[1], True, maxsplit=1)
            else:
                artist_a, group_a = split_enclosed(parts[0], True, maxsplit=1)
                artist_b, group_b = split_enclosed(parts[1], True, maxsplit=1)

            return Name.from_parts((artist_a, artist_b), extra={'group': Name.from_parts((group_a, group_b))})
        elif ends_with_enclosed(parts[0]) and LangCat.categorize(parts[0]) == LangCat.MIX:
            return Name.from_parts(
                split_enclosed(parts[0], True, maxsplit=1),
                extra={'group': Name.from_enclosed(parts[1])},
            )
        else:
            return self._default_artist_name(part, parts)

    def _default_artist_name(self, part: str | Sequence[str], parts: Collection[str]) -> Name:
        # log.debug(f'No custom action for {parts=}')
        name = Name.from_enclosed(part) if isinstance(part, str) else Name.from_parts(parts)

        if name._english and not name.extra:
            if ' of ' in name._english:
                name._english, _, group = name._english.partition(' of ')
                name.extra = {'group': Name.from_enclosed(group)}
            elif ' (' in name._english:
                name._english, group = split_enclosed(name._english, True, maxsplit=1)
                name.extra = {'group': Name.from_enclosed(group)}

        return name

    # endregion

    # region Split Artist List

    @cached_property
    def _unzipped_pat(self) -> Pattern:
        return re.compile(r'([;,&]| [x×] ).*?[(\[].*?\1', re.IGNORECASE)

    @cached_property
    def _delimiter_pat(self) -> Pattern:
        # return re.compile(r'(?:[;,&]| [x×] (?!\())', re.IGNORECASE)
        return re.compile(r'[;,&]| [x×] (?!\()', re.IGNORECASE)

    def _contains_delim(self, text: str):
        return self._delimiter_pat.search(text)

    def _unzipped_list_pairs(self, text: str) -> Iterable[tuple[str, str]] | None:
        if not self._unzipped_pat.search(text):
            return None

        parts: tuple[str, str] = split_enclosed(text, True, maxsplit=1)
        # log.debug(f'Found unzipped list:\n > a = {parts[0]!r}\n > b = {parts[1]!r}')
        if parts[0].count(',') == parts[1].count(','):
            # log.debug(f'Split {parts=}')
            return zip(*map(self.split_str_list, parts))
        elif self._contains_delim(parts[1]):
            # log.debug(f' > Delimiter counts did not match')
            return self._unzip_unbalanced(parts)
        else:
            return None

    def _unzip_unbalanced(self, parts: tuple[str, str]) -> Iterable[tuple[str, str]] | None:
        pairs = []
        parts_a, parts_b = list(self.split_str_list(parts[0], True)), list(self.split_str_list(parts[1], True))
        while parts_a and parts_b:
            a = parts_a.pop()
            b = parts_b.pop()
            if a == b:
                pairs.append((a,))
            elif all(ends_with_enclosed(p) for p in (a, b)):
                try:
                    if self._contains_delim(a):
                        pairs.extend(self._balance_unzipped_parts(parts_b, a, b))
                    elif self._contains_delim(b):
                        pairs.extend(self._balance_unzipped_parts(parts_a, b, a))
                    else:
                        pairs.append((a, b))
                except UnexpectedListLength:
                    log.debug(f'Unexpected end of unbalanced unzipped list for {parts=}')
                    return None
            else:
                pairs.append((a, b))
        return pairs

    def _balance_unzipped_parts(self, parts: MutableSequence[str], a: str, b: str) -> Iterator[tuple[str, str]]:
        group_a, a_members = split_enclosed(a, True, maxsplit=1)
        members = list(self.split_str_list(a_members, reverse=True))
        while members and (mem_x := members.pop()):
            if b is None:
                raise UnexpectedListLength
            mem_y, group_b = split_enclosed(b, True, maxsplit=1)
            yield f'{mem_x} ({mem_y})', f'of {group_a} ({group_b})'
            b = parts.pop() if members and parts else None

    # endregion

    # region Split String List

    def split_str_list(self, text: str, reverse: bool = False) -> Iterable[str]:
        """
        Split a list of artists on common delimiters, while preserving enclosed lists of artists that should be grouped
        together
        """
        # log.debug(f'Splitting {text=}')
        processed = []
        processing = []
        for i, part in enumerate(self._split_str_list(text)):
            part = fix_apostrophes(part)
            kwargs = {'exclude': "'"} if part.count("'") % 2 == 1 else {}
            if has_unpaired(part, **kwargs):
                if processing:
                    processing.append(part)
                    processed.append(''.join(processing))
                    processing = []
                else:
                    processing.append(part)
            elif processing:
                processing.append(part)
            elif i % 2 == 0:
                processed.append(part)
            # else:
            #     log.debug(f'Discarding {part=}')

        if processing:
            # for part in processing:
            #     log.debug(f'Incomplete {part=}:')
            #     for c in part:
            #         log.debug(f'ord({c=}) = {ord(c)}')
            raise UnexpectedListFormat(f'Unexpected str list format for {text=} -\n{processed=}\n{processing=}')

        return map(str.strip, processed[::-1] if reverse else processed)

    def _split_str_list(self, text: str) -> Iterator[str]:
        """Split a list of artists on common delimiters"""
        last = 0
        after = None
        for m in self._delimiter_pat.finditer(text):
            start, end = m.span()
            yield text[last:start]  # before
            yield text[start:end]   # delim
            after = text[end:]
            last = end
            # log.debug(f'{before=} {delim=} {after=}')

        if after:
            yield after
        elif last == 0:
            yield text

    # endregion


split_artists = _ArtistSplitter().split_artists


def _langs_match(parts):
    iparts = iter(parts)
    lang = LangCat.categorize(next(iparts))
    for part in iparts:
        if LangCat.categorize(part) != lang:
            return False
    return True


class UnexpectedListFormat(ValueError):
    """Exception to be raised when an unexpected str list format is encountered"""


class UnexpectedListLength(ValueError):
    """Exception to be raised when an unexpected number of elements are in an unbalanced unzipped list"""
