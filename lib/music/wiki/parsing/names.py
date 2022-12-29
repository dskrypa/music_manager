"""
Common name parsing utilities.
"""

from __future__ import annotations

import logging
from typing import Collection, Mapping, Iterator

from wiki_nodes.nodes import Link, AnyNode, Node, MappingNode

from music.text.name import Name

__all__ = ['parse_artists', 'parse_artist', 'parse_track_artists']
log = logging.getLogger(__name__)

LinkMap = Mapping[str, Link]


def parse_artists(artists: AnyNode | str, links: LinkMap | AnyNode | None = None) -> list[Name]:
    artists, links = _normalize_artists_links(artists, links)
    return [_parse_artist(name_str, links) for name_str in map(str.strip, artists.split(',')) if name_str]


def parse_artist(artist: AnyNode | str, links: LinkMap | AnyNode | None = None) -> Name:
    artists = parse_artists(artist, links)
    try:
        first_artist = artists[0]
    except IndexError as e:
        raise ValueError(f'No artist names could be parsed from {artist=}') from e
    if len(artists) > 1:
        raise ValueError(f'Found too many ({len(artists)}) artists in {artist=}')
    return first_artist


def _normalize_artists_links(artists: AnyNode | str, links: LinkMap | AnyNode | None) -> tuple[str, LinkMap]:
    links = _get_link_map(artists if links is None and isinstance(artists, Node) else links)
    if not isinstance(artists, str):
        artists = ' '.join(artists.strings())
    return artists, links


def _parse_artist(name_str: str, links: LinkMap) -> Name:
    extra = {}
    name_str, _, group = name_str.partition(' of ')
    if group:
        extra['group'] = _parse_artist(group, links)

    name = Name.from_enclosed(name_str, extra=extra)
    if relevant_links := _filter_links({name_str, *name}, links):
        name.update_extra(links=relevant_links)

    return name


def _get_link_map(node: AnyNode | None) -> LinkMap:
    if not node:
        return {}
    elif isinstance(node, Link):
        return {node.show: node} if node.show else {}
    elif isinstance(node, Mapping) and not isinstance(node, MappingNode):
        return {key: val for key, val in node.items() if key}
    return {link.show: link for link in node.find_all(Link, recurse=True) if link.show}


def _filter_links(keys: Collection[str], links: LinkMap) -> list[Link]:
    filtered = []
    for key in keys:
        try:
            filtered.append(links[key])
        except KeyError:
            pass
    filtered.sort()
    return filtered


def parse_track_artists(artists: AnyNode | str, links: LinkMap | AnyNode | None = None) -> list[str | Link]:
    artists_str, link_map = _normalize_artists_links(artists, links)
    return [part for part in _parse_track_artists(artists_str, link_map)]


def _parse_track_artists(artists_str: str, link_map: LinkMap) -> Iterator[str | Link]:
    non_artist = []
    last_str = artists_str
    last_same = 0
    while artists_str:
        last_same += int(last_str == artists_str)
        if last_same > 1:
            raise ValueError(f'Unexpected {artists_str=} / link_map content')

        for text, link in link_map.items():
            if artists_str.startswith(text):
                if non_artist:
                    yield ' '.join(non_artist)
                    non_artist = []
                yield link
                last_str = artists_str
                artists_str = artists_str[len(text):].strip()
                break
        else:
            last_str = artists_str
            try:
                part, artists_str = artists_str.split(maxsplit=1)
            except ValueError:
                non_artist.append(artists_str)
                break
            else:
                non_artist.append(part)

    if non_artist:
        yield ' '.join(non_artist)
