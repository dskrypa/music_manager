"""
Common name parsing utilities.
"""

from __future__ import annotations

from typing import Collection, Mapping

from wiki_nodes.nodes import Link, AnyNode, Node, MappingNode

from music.text.name import Name

__all__ = ['parse_artists', 'parse_artist']

LinkMap = Mapping[str, Link]


def parse_artists(artists: AnyNode | str, links: LinkMap | AnyNode | None = None) -> list[Name]:
    links = _get_link_map(artists if links is None and isinstance(artists, Node) else links)
    if not isinstance(artists, str):
        artists = ' '.join(artists.strings())

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
        return {node.show: node}
    elif isinstance(node, Mapping) and not isinstance(node, MappingNode):
        return node
    return {link.show: link for link in node.find_all(Link, recurse=True)}


def _filter_links(keys: Collection[str], links: LinkMap) -> list[Link]:
    filtered = []
    for key in keys:
        try:
            filtered.append(links[key])
        except KeyError:
            pass
    filtered.sort()
    return filtered
