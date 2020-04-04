"""
:author: Doug Skrypa
"""

import logging
from functools import partialmethod
from typing import TYPE_CHECKING, Any, List, Optional

from ds_tools.compat import cached_property
from wiki_nodes.nodes import CompoundNode, String, Link
from ..text import Name, combine_with_parens
from .artist import Artist

if TYPE_CHECKING:
    from .album import DiscographyEntryPart

__all__ = ['Track']
log = logging.getLogger(__name__)
EXTRA_VALUE_MAP = {'instrumental': 'Inst.', 'acoustic': 'Acoustic'}
PATH_FORMATS = {
    'alb_type_with_num': '{artist}/{album_type}/[{date}] {album} [{album_num}]/{num}. {track}.{ext}',
    'alb_type_no_num': '{artist}/{album_type}/[{date}] {album}/{num}. {track}.{ext}',
}


class Track:
    def __init__(self, num: int, name: Name, album_part: Optional['DiscographyEntryPart']):
        self.num = num                  # type: int
        self.name = name                # type: Name
        self.album_part = album_part    # type: Optional[DiscographyEntryPart]

    def _repr(self, long=False):
        if long:
            return f'<{self.__class__.__name__}[{self.num:02d}: {self.name!r} @ {self.album_part}]>'
        return f'<{self.__class__.__name__}[{self.num:02d}: {self.name!r}]>'

    __repr__ = partialmethod(_repr, True)

    def __lt__(self, other: 'Track'):
        return (self.album_part, self.num, self.name) < (other.album_part, other.num, other.name)

    def __getitem__(self, item: str) -> Any:
        if extras := self.name.extra:
            return extras[item]
        else:
            raise KeyError(item)

    @cached_property
    def collab_parts(self) -> List[str]:
        parts = []
        if extras := self.name.extra:
            if feat := extras.get('feat'):
                if isinstance(feat, CompoundNode):
                    feat = artist_string(feat)
                parts.append(f'feat. {feat}')
            if collab := extras.get('collabs'):
                if isinstance(collab, CompoundNode):
                    collab = artist_string(collab)
                parts.append(f'with {collab}')
        return parts

    def full_name(self, collabs=True) -> str:
        """
        :param bool collabs: Whether collaborators / featured artists should be included
        :return str: This track's full name
        """
        name_obj = self.name
        parts = [str(name_obj)]
        if extras := name_obj.extra:
            parts.extend(val for key, val in EXTRA_VALUE_MAP.items() if extras.get(key))

            for key in ('version', 'edition'):
                if value := extras.get(key):
                    parts.append(value)

            if collabs:
                parts.extend(self.collab_parts)

        return combine_with_parens(parts)

    def format_path(self, fmt: str = PATH_FORMATS['alb_type_no_num'], ext: str = 'mp3'):
        album_part = self.album_part
        edition = album_part.edition
        artist_name = edition.artist.english if edition.artist else edition._artist.show
        if edition.edition:
            album_name = f'{edition.name} - {edition.edition}'
        else:
            album_name = str(edition.name)
        args = {
            'artist': artist_name,
            'album_type': edition.type.real_name,
            'date': edition.date.strftime('%Y.%m.%d'),
            'album': album_name,
            'album_num': None,
            'num': self.num,
            'track': self.name,
            'ext': ext
        }
        return fmt.format(**args)


def artist_string(node: CompoundNode) -> str:
    link_artist_map = Artist.from_links(node.find_all(Link))
    parts = []
    for child in node.children:
        if isinstance(child, String):
            parts.append(child.value)
            # value = child.value.strip()
            # if value not in '()':
            #     feat_parts.append(value)
        elif isinstance(child, Link):
            try:
                parts.append(link_artist_map[child].name)
            except KeyError:
                parts.append(child.show)

    # log.debug(f'Artist string parts: {parts}')
    processed = []
    last = None
    for part in map(str, parts):
        if part:
            if last == ')':
                if not part.startswith(')'):
                    processed.append(' ')
            elif last and last not in ' (':
                processed.append(' ')
            processed.append(part)
            last = part[-1]

    return ''.join(processed)
