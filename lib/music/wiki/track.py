"""
:author: Doug Skrypa
"""

from __future__ import annotations

import logging
from itertools import chain
from functools import partialmethod, cached_property
from typing import TYPE_CHECKING, Any, Optional, Iterable

from wiki_nodes import String, Link, ContainerNode
from ..text.extraction import strip_enclosed
from ..text.name import Name
from ..text.utils import combine_with_parens
from .parsing.utils import replace_lang_abbrev
from .artist import Artist

if TYPE_CHECKING:
    from .album import DiscographyEntryPart

__all__ = ['Track']
log = logging.getLogger(__name__)

EXTRA_VALUE_MAP = {'instrumental': 'Inst.', 'acoustic': 'Acoustic'}
ARTISTS_SUFFIXES = {1: 'solo', 2: 'duet'}


class Track:
    def __init__(self, num: int, name: Name, album_part: Optional[DiscographyEntryPart]):
        self.num = num                  # type: int
        self.name = name                # type: Name
        self.album_part = album_part    # type: Optional[DiscographyEntryPart]
        self._collabs = []

    def _repr(self, long: bool = False) -> str:
        if long:
            return f'<{self.__class__.__name__}[{self.num:02d}: {self.name!r} @ {self.album_part}]>'
        return f'<{self.__class__.__name__}[{self.num:02d}: {self.name!r}]>'

    __repr__ = partialmethod(_repr, True)

    def __lt__(self, other: Track) -> bool:
        return (self.album_part, self.num, self.name) < (other.album_part, other.num, other.name)

    def __getitem__(self, item: str) -> Any:
        if extras := self.name.extra:
            return extras[item]
        else:
            raise KeyError(item)

    @cached_property
    def artists(self) -> set[Artist]:
        if (extras := self.name.extra) and (artists := extras.get('artists')):
            if isinstance(artists, ContainerNode):
                link_artist_map = Artist.from_links(artists.find_all(Link))  # noqa
                return set(link_artist_map.values())
            elif isinstance(artists, Link):
                try:
                    artist = Artist.from_link(artists)  # noqa
                except Exception as e:
                    log.debug(f'Error retrieving artist from link={artists!r}: {e}')
                else:
                    return {artist}
        return set()

    def add_collabs(self, artists):
        self._collabs.extend(artists)

    @cached_property
    def collab_parts(self) -> list[str]:
        return self._collab_parts(True)

    def _collab_parts(self, suffixes: bool = True) -> list[str]:
        parts = []
        if extras := self.name.extra:
            if feat := extras.get('feat'):
                if isinstance(feat, ContainerNode):
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
                if isinstance(collab, ContainerNode):
                    collab = artist_string(collab)[0]
                parts.append(f'with {collab}')

            if artists := extras.get('artists'):
                if isinstance(artists, ContainerNode):
                    artists, found = artist_string(artists)
                    if suffixes and (suffix := ARTISTS_SUFFIXES.get(found)):
                        artists = f'{artists} {suffix}'  # noqa
                elif isinstance(artists, Link):
                    try:
                        artist = Artist.from_link(artists)
                    except Exception as e:
                        log.debug(f'Error retrieving artist from link={artists!r}: {e}')
                    else:
                        artists = f'{artist.name} solo' if suffixes else str(artist.name)

                parts.append(str(artists))

        return parts

    def artist_name(self, artist_name: str, collabs: bool = True) -> str:
        if artist_name == 'Various Artists':
            if collabs and (parts := self._collab_parts(False)):
                return ' '.join(parts)  # noqa
            else:
                parts = ()
        else:
            parts = chain((artist_name,), (str(a.name) for a in self._collabs))

        base = ', '.join(parts)
        if collabs and (parts := self.collab_parts):
            if base:
                collab_str = ' '.join(f'({part})' for part in parts)
                return f'{base} {collab_str}'
            return ' '.join(parts)
        return base

    def full_name(self, collabs: bool = True) -> str:
        """
        :param collabs: Whether collaborators / featured artists should be included
        :return: This track's full name
        """
        name_obj = self.name
        parts = [strip_enclosed(str(name_obj), exclude='])')]
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

    @cached_property
    def extras(self):
        if extras := self.name.extra:
            return extras
        return {}


def artist_string(node: ContainerNode) -> tuple[str, int]:
    found = 0
    link_artist_map = Artist.from_links(node.find_all(Link))
    # log.debug(f'Found {link_artist_map=}')
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
            if last and part == ', &':
                part = ' & '
            elif last == ')':
                if not part.startswith(')') and part != ',':
                    processed.append(' ')
            elif last and last not in ' (' and part != ',':
                processed.append(' ')
            processed.append(part)
            last = part[-1]

    return ''.join(processed), found
