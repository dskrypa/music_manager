"""
:author: Doug Skrypa
"""

import logging
from itertools import chain
from functools import partialmethod
from typing import TYPE_CHECKING, Any, List, Optional, Tuple, Iterable

from ds_tools.compat import cached_property
from wiki_nodes import CompoundNode, String, Link
from ..text import Name, combine_with_parens
from .parsing.utils import replace_lang_abbrev
from .artist import Artist

if TYPE_CHECKING:
    from .album import DiscographyEntryPart

__all__ = ['Track']
log = logging.getLogger(__name__)
EXTRA_VALUE_MAP = {'instrumental': 'Inst.', 'acoustic': 'Acoustic'}
ARTISTS_SUFFIXES = {1: 'solo', 2: 'duet'}


class Track:
    def __init__(self, num: int, name: Name, album_part: Optional['DiscographyEntryPart']):
        self.num = num                  # type: int
        self.name = name                # type: Name
        self.album_part = album_part    # type: Optional[DiscographyEntryPart]
        self._collabs = []

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

    def add_collabs(self, artists):
        self._collabs.extend(artists)

    @cached_property
    def collab_parts(self) -> List[str]:
        parts = []
        if extras := self.name.extra:
            if feat := extras.get('feat'):
                if isinstance(feat, CompoundNode):
                    feat = artist_string(feat)[0]
                elif isinstance(feat, Link):
                    try:
                        feat = Artist.from_link(feat)
                    except Exception as e:
                        log.debug(f'Error retrieving artist from link={feat!r}: {e}')
                    else:
                        feat = feat.name

                parts.append(f'feat. {feat}')
            if collab := extras.get('collabs'):
                if isinstance(collab, CompoundNode):
                    collab = artist_string(collab)[0]
                parts.append(f'with {collab}')

            if artists := extras.get('artists'):
                if isinstance(artists, CompoundNode):
                    artists, found = artist_string(artists)
                    if suffix := ARTISTS_SUFFIXES.get(found):
                        artists = f'{artists} {suffix}'
                elif isinstance(artists, Link):
                    try:
                        artist = Artist.from_link(artists)
                    except Exception as e:
                        log.debug(f'Error retrieving artist from link={artists!r}: {e}')
                    else:
                        artists = f'{artist.name} solo'

                parts.append(str(artists))

        return parts

    def artist_name(self, artist_name, collabs=True):
        base = ', '.join(chain((artist_name,), (str(a.name) for a in self._collabs)))
        if collabs and (parts := self.collab_parts):
            # noinspection PyUnboundLocalVariable
            return '{} {}'.format(base, ' '.join(f'({part})' for part in parts))
        return base

    def full_name(self, collabs=True) -> str:
        """
        :param bool collabs: Whether collaborators / featured artists should be included
        :return str: This track's full name
        """
        name_obj = self.name
        parts = [str(name_obj)]
        if extras := name_obj.extra:
            parts.extend(val for key, val in EXTRA_VALUE_MAP.items() if extras.get(key))

            for key in ('version', 'edition', 'remix'):
                if value := extras.get(key):
                    if isinstance(value, str):
                        parts.append(replace_lang_abbrev(value))
                    elif isinstance(value, Iterable):
                        parts.extend(replace_lang_abbrev(v) for v in value)
                    else:
                        log.debug(f'Unexpected value for {self}.name.extra[{key!r}]: {value!r}')

            if collabs:
                parts.extend(self.collab_parts)

        return combine_with_parens(parts)


def artist_string(node: CompoundNode) -> Tuple[str, int]:
    found = 0
    link_artist_map = Artist.from_links(node.find_all(Link))
    parts = []
    for child in node.children:
        if isinstance(child, String):
            parts.append(child.value)
            # value = child.value.strip()
            # if value not in '()':
            #     feat_parts.append(value)
        elif isinstance(child, Link):
            found += 1
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

    return ''.join(processed), found
