"""
:author: Doug Skrypa
"""

import logging
import re
from typing import Tuple, Optional, List, Iterator, Sequence, Union

from ds_tools.unicode.languages import LangCat
from ...text import Name, split_enclosed, has_unpaired, sort_name_parts, ends_with_enclosed, get_unpaired

__all__ = ['AlbumName', 'split_artists', 'UnexpectedListFormat']
log = logging.getLogger(__name__)

ATTR_NAMES = {'alb_type': 'type', 'sm_station': 'SM', 'version': 'ver', 'alb_num': 'num', 'ost': 'OST'}
APOSTROPHES = "'`՚՛՜՝‘’"
APOSTROPHES_TRANS = str.maketrans({c: "'" for c in APOSTROPHES})
CHANNELS = tuple(map(str.lower, ('SBS', 'KBS', 'tvN', 'MBC')))

ALB_TYPE_DASH_SUFFIX_MATCH = re.compile(r'(.*)\s[-X]\s*((?:EP|Single|SM[\s-]?STATION))$', re.IGNORECASE).match
NTH_ALB_TYPE_MATCH = re.compile(
    r'^(?:the)?\s*([0-9]+(?:st|nd|rd|th))\s+(.*?album\s*(?:repackage)?)$', re.IGNORECASE
).match
OST_PART_MATCH = re.compile(r'(.*?)\s((?:O\.?S\.?T\.?)?)\s*-?\s*((?:Part|Code No)?)\.?\s*(\d+)$', re.IGNORECASE).match
SPECIAL_PREFIX_MATCH = re.compile(r'^(\S+\s+special)\s+(.*)$', re.IGNORECASE).match

DELIMS_PAT = re.compile('(?:[;,&]| [x×] )', re.IGNORECASE)
CONTAINS_DELIM = DELIMS_PAT.search
DELIM_FINDITER = DELIMS_PAT.finditer
UNZIPPED_LIST_MATCH = re.compile(r'([;,&]| [x×] ).*?[(\[].*?\1', re.IGNORECASE).search


class AlbumName:
    alb_type, alb_num, sm_station, edition, remix, version, ost, part = None, None, None, None, None, None, False, None
    network_info, name, part_name, feat, song_name = None, None, None, None, None

    def __init__(self, name_parts, **kwargs):
        if isinstance(name_parts, str):
            self.name = Name(name_parts)
        else:
            self.name = Name(*sort_name_parts(name_parts))
        self.__dict__.update(kwargs)

    def __repr__(self):
        # parts = ', '.join(sorted(
        #     f'{ATTR_NAMES.get(k, k)}={v!r}' for k, v in self.__dict__.items() if v and k != 'name'
        # ))
        parts = ', '.join(sorted(f'{k}={v!r}' for k, v in self.__dict__.items() if v and k != 'name'))
        parts = f', {parts}' if parts else ''
        # return f'<{self.__class__.__name__}[name={self.name!r}{parts}]>'
        return f'{self.__class__.__name__}({self.name!r}{parts})'

    def __eq__(self, other):
        if not isinstance(other, self.__class__):
            return False
        # log.debug(f'Comparing self={self.__dict__} to other={other.__dict__}')
        return self.__dict__ == other.__dict__

    @classmethod
    def parse(cls, name):
        self = cls.__new__(cls)
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
                self.part = int(part_num)
                name = _name

        real_album = None
        feat = []
        try:
            parts = list(filter(None, map(clean, reversed(split_enclosed(name, reverse=True)))))
        except ValueError:
            name_parts = (name.translate(APOSTROPHES_TRANS),)
        else:
            name_parts = []
            for i, part in enumerate(parts):
                part = part.translate(APOSTROPHES_TRANS)
                lc_part = part.lower()
                # log.debug(f'Processing part={part!r} / lc_part={lc_part!r}')
                if self.ost and part == '영화':   # movie
                    pass
                elif 'edition' in lc_part:
                    self.edition = part
                elif 'remix' in lc_part:
                    self.remix = part
                elif any(lc_part.endswith(val) for val in (' version', ' ver.', ' ver', ' 버전')):
                    try:
                        if ost_idx := lc_part.index(' ost '):
                            self.ost = True
                            real_album = clean(part[:ost_idx])
                            self.version = clean(part[ost_idx+5:])
                        else:
                            self.version = part
                    except ValueError:
                        self.version = part
                elif lc_part.endswith('single'):
                    self.alb_type = part
                elif lc_part.startswith(('feat', 'with ')):
                    try:
                        feat_artist = part.split(maxsplit=1)[1]
                    except IndexError:
                        name_parts.append(part)
                    else:
                        feat.append(feat_artist)
                elif lc_part.startswith(CHANNELS) and (lc_part.endswith('드라마') or '특별' in lc_part):
                    self.network_info = part
                elif suffix := next((s for s in ('original soundtrack', ' ost') if lc_part.endswith(s)), None):
                    part = clean(part[:-len(suffix)])
                    self.ost = True
                    if len(parts) == 2 and 'OST' not in parts[int(not i)]:
                        real_album = part
                        part = None
                    if part:
                        name_parts.append(part)
                elif m := OST_PART_MATCH(part):
                    _part, _ost, _part_, part_num = map(clean, m.groups())
                    if _part_ or _ost:
                        self.ost = True
                        self.part = int(part_num)
                        part = _part
                        if len(parts) == 2 and 'OST' not in parts[int(not i)]:
                            real_album = part
                            part = None

                    if part:
                        name_parts.append(part)
                elif m := NTH_ALB_TYPE_MATCH(part):
                    self.alb_num = '{} {}'.format(*m.groups())
                    self.alb_type = m.group(2)
                elif m := SPECIAL_PREFIX_MATCH(part):
                    self.alb_type, part = map(clean, m.groups())
                    if part:
                        name_parts.append(part)
                else:
                    name_parts.append(part)

        if feat:
            self.feat = feat

        if real_album:
            if name_parts:
                self.song_name = Name(*sort_name_parts(split_name(tuple(reversed(name_parts)))))
            name_parts = (real_album,)
        else:
            name_parts = split_name(tuple(reversed(name_parts)))

        self.name = Name(*sort_name_parts(name_parts))
        return self


def split_name(name_parts):
    if len(name_parts) == 1:
        name = name_parts[0]
        if LangCat.categorize(name) == LangCat.MIX:
            name_parts = split_enclosed(name)
            if len(name_parts) == 1 and ' - ' in name:
                name_parts = tuple(map(clean, name.split(' - ')))
    return name_parts


def clean(text):
    return text.strip(' -"')


def _split_str_list(text: str) -> Iterator[str]:
    """Split a list of artists on common delimiters"""
    last = 0
    after = None
    for m in DELIM_FINDITER(text):
        start, end = m.span()
        before = text[last:start]
        delim = text[start:end]
        after = text[end:]
        last = end
        # log.debug(f'{before=!r} {delim=!r} {after=!r}')
        yield before
        yield delim

    if after:
        yield after
    elif last == 0:
        yield text


def split_str_list(text: str):
    """
    Split a list of artists on common delimiters, while preserving enclosed lists of artists that should be grouped
    together
    """
    # log.debug(f'Splitting {text=!r}')
    processed = []
    processing = []
    for i, part in enumerate(_split_str_list(text)):
        part = part.translate(APOSTROPHES_TRANS)
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
        #     log.debug(f'Discarding {part=!r}')

    if processing:
        # for part in processing:
        #     log.debug(f'Incomplete {part=!r}:')
        #     for c in part:
        #         log.debug(f'ord({c=!r}) = {ord(c)}')
        raise UnexpectedListFormat(f'Unexpected str list format for {text=!r} -\n{processed=}\n{processing=}')
    return map(str.strip, processed)


def split_artists(text: str) -> List[Name]:
    try:
        return _split_artists(text)
    except UnexpectedListFormat:
        if ends_with_enclosed(text) and get_unpaired(text) == '(':
            return _split_artists(text + ')')
        raise


def _split_artists(text: str) -> List[Name]:
    artists = []
    if parts := _unzipped_list_parts(text):
        # log.debug(f'Split {parts=}')
        for pair in zip(*map(split_str_list, parts)):
            # log.debug(f'Found {pair=!r}')
            artists.append(_artist_name(pair))
    else:
        for part in split_str_list(text):
            # log.debug(f'Found {part=!r}')
            artists.append(_artist_name(part))

    return artists


def _artist_name(part: Union[str, Sequence[str]]) -> Name:
    parts = split_enclosed(part, True, maxsplit=1) if isinstance(part, str) else part
    part_count = len(parts)
    if part_count == 2 and CONTAINS_DELIM(parts[1]):
        # log.debug(f'Split group/members {parts=}')
        name = Name.from_enclosed(parts[0])
        name.extra = {'members': split_artists(parts[1])}
    elif part_count == 2 and parts[1].startswith(('from ', 'of ')):
        # log.debug(f'Split soloist/group {parts=}')
        name = Name.from_enclosed(parts[0])
        name.extra = {'group': Name.from_enclosed(parts[1].split(maxsplit=1)[1])}
    elif part_count == 2 and all(ends_with_enclosed(p) for p in parts):
        if all(LangCat.categorize(p) == LangCat.MIX for p in parts):
            artist_a, artist_b = split_enclosed(parts[0], True, maxsplit=1)
            group_a, group_b = split_enclosed(parts[1], True, maxsplit=1)
        else:
            artist_a, group_a = split_enclosed(parts[0], True, maxsplit=1)
            artist_b, group_b = split_enclosed(parts[1], True, maxsplit=1)

        name = Name.from_parts((artist_a, artist_b))
        name.extra = {'group': Name.from_parts((group_a, group_b))}
    elif part_count == 2 and ends_with_enclosed(parts[0]) and LangCat.categorize(parts[0]) == LangCat.MIX:
        artist_a, artist_b = split_enclosed(parts[0], True, maxsplit=1)
        name = Name.from_parts((artist_a, artist_b))
        name.extra = {'group': Name.from_enclosed(parts[1])}
    else:
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


def _unzipped_list_parts(text: str) -> Optional[Tuple[str, str]]:
    if UNZIPPED_LIST_MATCH(text):
        parts = split_enclosed(text, True, maxsplit=1)
        if parts[0].count(',') == parts[1].count(','):
            # noinspection PyTypeChecker
            return parts
    return None


class UnexpectedListFormat(ValueError):
    """Exception to be raised when an unexpected str list format is encountered"""
