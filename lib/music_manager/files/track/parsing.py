"""
:author: Doug Skrypa
"""

import logging
import re

from ds_tools.unicode.languages import LangCat
from ...matching.name import Name
from ...text.extraction import split_enclosed

__all__ = ['AlbumName']
log = logging.getLogger(__name__)

APOSTROPHES = str.maketrans({c: "'" for c in '`՚՛՜՝‘’'})
CHANNELS = tuple(map(str.lower, ('SBS', 'KBS', 'tvN', 'MBC')))

ALB_TYPE_DASH_SUFFIX_MATCH = re.compile(r'(.*)\s[-X]\s*((?:EP|Single|SM[\s-]?STATION))$', re.IGNORECASE).match
NTH_ALB_TYPE_MATCH = re.compile(
    r'^(?:the)?\s*([0-9]+(?:st|nd|rd|th))\s+(.*?album\s*(?:repackage)?)$', re.IGNORECASE
).match
OST_PART_MATCH = re.compile(r'(.*?)\s((?:O\.?S\.?T\.?)?)\s*-?\s*((?:Part|Code No)?\.?\s*(\d+))$', re.IGNORECASE).match


class AlbumName:
    alb_type, alb_num, sm_station, edition, remix, version, ost, part = None, None, None, None, None, None, False, None
    network_info, name, part_name = None, None, None

    def __init__(self, name):
        """
        :param str name:
        """
        m = ALB_TYPE_DASH_SUFFIX_MATCH(name)
        if m:
            name, alb_type = map(clean, m.groups())
            if 'station' in alb_type.lower():
                self.sm_station = True
            else:
                self.alb_type = alb_type

        if name.endswith(' OST'):
            name = clean(name[:-4])
            self.ost = True
        else:
            m = OST_PART_MATCH(name)
            if m:
                _name, _ost, _part, part_num = map(clean, m.groups())
                if _part or _ost:
                    # print(f'  > OST match: {m.groups()}')
                    self.ost = True
                    self.part = int(part_num)
                    name = _name

        self.feat = []
        try:
            parts = filter(None, map(clean, reversed(split_enclosed(name, reverse=True, recurse=1))))
        except ValueError:
            name_parts = (name.translate(APOSTROPHES),)
        else:
            name_parts = []
            for i, part in enumerate(parts):
                part = part.translate(APOSTROPHES)
                lc_part = part.lower()
                if 'edition' in lc_part:
                    self.edition = part
                elif 'remix' in lc_part:
                    self.remix = part
                elif any(lc_part.endswith(val) for val in (' version', ' ver.', ' ver')):
                    self.version = part
                elif lc_part.endswith('single'):
                    self.alb_type = part
                elif lc_part.startswith('feat'):
                    self.feat.append(part)
                elif lc_part.endswith(' ost'):
                    part = clean(part[:-4])
                    self.ost = True
                    if part:
                        name_parts.append(part)
                elif lc_part.startswith(CHANNELS) and (lc_part.endswith('드라마') or '특별' in lc_part):
                    self.network_info = part
                elif lc_part.endswith('original soundtrack'):
                    part = clean(part[:-19])
                    self.ost = True
                    if part:
                        name_parts.append(part)
                else:
                    m = NTH_ALB_TYPE_MATCH(part)
                    if m:
                        self.alb_num = '{} {}'.format(*m.groups())
                        self.alb_type = m.group(2)
                    else:
                        m = OST_PART_MATCH(part)
                        if m:
                            _part, _ost, _part_, part_num = map(clean, m.groups())
                            if _part_ or _ost:
                                # print(f'  > OST match: {m.groups()}')
                                self.ost = True
                                self.part = int(part_num)
                                part = _part

                        if part:
                            name_parts.append(part)

        self.name_parts = tuple(reversed(name_parts))
        # if self.ost:
        #     a, extras, b = sort_ost_name_parts(name_parts)
        #     self.name = Name(*a, extra=extras)
        #     if b:
        #         self.part_name = Name(*b)
        # else:
        #     name_parts = sort_name_parts(name_parts, '')

    def __repr__(self):
        parts = ', '.join((
            f'type={self.alb_type!r}, SM={self.sm_station}, ver={self.version!r}, edition={self.edition!r}',
            f'remix={self.remix!r}, feat={self.feat!r}, num={self.alb_num!r}, OST={self.ost}, part={self.part}',
            f'network_info={self.network_info!r}'
        ))
        return f'<{self.__class__.__name__}[name={self.name_parts!r}, {parts}]>'


def clean(text):
    text = text.strip()
    if text.startswith('- '):
        text = text[2:].strip()
    if text.endswith(' -'):
        text = text[-2:].strip()
    if text == '-':
        text = ''
    return text

#
# def sort_name_parts(parts, punctuation):
#     """
#
#     :param tuple|list parts:
#     :param punctuation: A string or iterable containing the punctuation that was removed from the original string while
#       extracting parts.  If successive parts have the same language category, they should be rejoined using the removed
#       punctuation.
#     :return tuple:
#     """
#     cats = LangCat.categorize_all(parts)
#     extras = None
#     part_count = len(parts)
#     if part_count == 1:
#         if cats[0] not in (LangCat.ENG, LangCat.MIX):
#             a = (None, parts[0])
#         else:
#             a = (parts[0], None)
#     elif part_count == 2:
#         pass
#
#
# def sort_ost_name_parts(parts):
#     cats = LangCat.categorize_all(parts)
#     extras, b = None, None
#     part_count = len(parts)
#     if part_count == 1:
#         if cats[0] not in (LangCat.ENG, LangCat.MIX):
#             a = (None, parts[0])
#         else:
#             a = (parts[0], None)
#     elif part_count == 2:
#         if cats[0] != cats[1]:
#             a = LangCat.sort(parts)
#         else:
#             a = parts
#     elif part_count == 3:
#         if cats[0] == cats[1] != cats[2]:
#             if cats[0] not in (LangCat.ENG, LangCat.MIX):
#                 a = (None, parts[0])
#             else:
#                 a = (parts[0], None)
#             b = LangCat.sort(parts[1:])
#         elif cats[1] == cats[2] != cats[0]:
#             if cats[2] not in (LangCat.ENG, LangCat.MIX):
#                 a = (None, parts[2])
#             else:
#                 a = (parts[2], None)
#             b = LangCat.sort(parts[:2])
#         # elif (cats[0] == cats[1] == cats[2]) or (cats[0] != cats[1] != cats[2]):
#         else:
#             a = parts[:2]
#             extras = parts[2]
#     elif part_count == 4:
#         a = parts[:2]
#         b = parts[2:]
#         if cats[0] != cats[1] != cats[2] != cats[3]:
#             a = LangCat.sort(a)
#             b = LangCat.sort(b)
#     else:
#         raise ValueError(f'Unexpected part count={part_count}: {parts!r}')
#     return a, extras, b
