"""
:author: Doug Skrypa
"""

import logging
import re

from ...text.extraction import split_enclosed

__all__ = ['AlbumName']
log = logging.getLogger(__name__)

ALB_TYPE_DASH_SUFFIX_MATCH = re.compile(r'(.*)\s[-X]\s*((?:EP|Single|SM[\s-]?STATION))$', re.IGNORECASE).match
NTH_ALB_TYPE_MATCH = re.compile(
    r'^(?:the)?\s*([0-9]+(?:st|nd|rd|th))\s+(.*?album\s*(?:repackage)?)$', re.IGNORECASE
).match


class AlbumName:
    # TODO: Handle OSTs / parts
    alb_type, alb_num, sm_station, edition, remix, version = None, None, None, None, None, None

    def __init__(self, name, artist=None):
        m = ALB_TYPE_DASH_SUFFIX_MATCH(name)
        if m:
            name, alb_type = map(str.strip, m.groups())
            if 'station' in alb_type.lower():
                self.sm_station = True
            else:
                self.alb_type = alb_type

        self.feat = []
        try:
            parts = filter(None, reversed(split_enclosed(name, reverse=True, recurse=1)))
        except ValueError:
            name_parts = (name,)
        else:
            name_parts = []
            for i, part in enumerate(parts):
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
                else:
                    m = NTH_ALB_TYPE_MATCH(part)
                    if m:
                        self.alb_num = '{} {}'.format(*m.groups())
                        self.alb_type = m.group(2)
                    else:
                        name_parts.append(part)
        self.name_parts = tuple(reversed(name_parts))

    def __repr__(self):
        parts = ', '.join((
            f'type={self.alb_type!r}, SM={self.sm_station}, ver={self.version!r}, edition={self.edition!r}',
            f'remix={self.remix!r}, feat={self.feat!r}, num={self.alb_num!r}'
        ))
        return f'<{self.__class__.__name__}[name={self.name_parts!r}, {parts}]>'
