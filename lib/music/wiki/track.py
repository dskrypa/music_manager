"""
:author: Doug Skrypa
"""

from __future__ import annotations

import logging
from itertools import chain
from functools import partialmethod
from typing import TYPE_CHECKING, Any, Optional, Iterable

from ds_tools.caching.decorators import cached_property
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

EXTRA_VALUE_MAP = {'instrumental': 'Inst.', 'acoustic': 'Acoustic', 'live': 'Live'}
ARTISTS_SUFFIXES = {1: 'solo', 2: 'duet'}


class Track:
    def __init__(self, num: int, name: Name, album_part: Optional[DiscographyEntryPart], disk: int = None):
        self.num = num                  # type: int
        self.name = name                # type: Name
        self.album_part = album_part    # type: Optional[DiscographyEntryPart]
        self._collabs = []
        self.disk = disk

    def _repr(self, long: bool = False) -> str:
        if long:
            return f'<{self.__class__.__name__}[{self.num:02d}: {self.name!r} @ {self.album_part}]>'
        return f'<{self.__class__.__name__}[{self.num:02d}: {self.name!r}]>'

    __repr__ = partialmethod(_repr, True)

    def __lt__(self, other: Track) -> bool:
        return (self.album_part, self.num, self.name) < (other.album_part, other.num, other.name)  # noqa

    def __getitem__(self, item: str) -> Any:
        if extras := self.name.extra:
            return extras[item]
        else:
            raise KeyError(item)

    @cached_property
    def artists(self) -> set[Artist]:
        extra = self.name.extra
        if not (artists := extra.get('artists') if extra else None):
            return set()

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
        else:
            log.debug(f'Unexpected value for track {artists=}')

        return set()

    def add_collabs(self, artists):
        self._collabs.extend(artists)

    @cached_property
    def collab_parts(self) -> list[str]:
        return self._collab_parts(True)

    def _collab_parts(self, suffixes: bool = True) -> list[str]:
        parts = []
        if not (extra := self.name.extra):
            return parts

        if feat := extra.get('feat'):
            if isinstance(feat, (ContainerNode, list)):
                feat = ArtistStringBuilder(feat).build_str()
            elif isinstance(feat, Link):
                try:
                    feat = Artist.from_link(feat)
                except Exception as e:
                    log.debug(f'Error retrieving artist from link={feat!r}: {e}')
                else:
                    feat = feat.name

            parts.append(f'feat. {feat}')

        if collab := extra.get('collabs'):
            if isinstance(collab, ContainerNode):
                collab = ArtistStringBuilder(collab).build_str()
            parts.append(f'with {collab}')

        if artists := extra.get('artists'):
            if isinstance(artists, ContainerNode):
                artists, found = ArtistStringBuilder(artists).build_and_found()
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

        if producer := extra.get('producer'):
            parts.append(f'Prod. {producer}')

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

            for key in ('version', 'edition', 'remix', 'remaster'):
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


class ArtistStringBuilder:
    __slots__ = ('found', 'children', 'link_artist_map')

    def __init__(self, node: ContainerNode | Iterable[Link | String]):
        self.found = 0
        try:
            self.children = node.children
        except AttributeError:
            self.children = node
            self.link_artist_map = Artist.from_links([obj for obj in node if isinstance(obj, Link)])
        else:
            self.link_artist_map = Artist.from_links(node.find_all(Link))
        # log.debug(f'Found {self.link_artist_map=}')

    def _iter_parts(self):
        for child in self.children:
            if isinstance(child, String):
                yield child.value
                # value = child.value.strip()
                # if value not in '()':
                #     feat_parts.append(value)
            elif isinstance(child, Link):
                self.found += 1
                try:
                    yield self.link_artist_map[child].name
                except KeyError:
                    if child.text:
                        yield child.text.strip()
                    elif child.title:
                        try:
                            title = child.iw_key_title[-1]
                        except ValueError:
                            yield child.title.strip()
                        else:
                            yield title[3:].strip() if title.lower().startswith('en:') else title.strip()
            elif isinstance(child, str):
                yield child

    def build_and_found(self) -> tuple[str, int]:
        return self.build_str(), self.found

    def build_str(self) -> str:
        parts = [p for p in map(str, self._iter_parts()) if p]
        log.debug(f'Artist string parts: {parts}')
        processed = []
        last = None
        for part in parts:
            if last and part == ', &':
                part = ' & '
            elif last == ')':
                if not part.startswith(')') and part != ',':
                    processed.append(' ')
            elif last and last not in ' (' and part != ',':
                processed.append(' ')

            processed.append(part)
            last = part[-1]

        return ''.join(processed)
