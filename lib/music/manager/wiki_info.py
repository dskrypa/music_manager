"""
:author: Doug Skrypa
"""

from itertools import count
from pathlib import Path
from typing import Optional, Iterable

from ds_tools.output.terminal import uprint
from wiki_nodes.http import MediaWikiClient
from wiki_nodes.http.utils import URL_MATCH
from wiki_nodes.page import WikiPage

from ..common.disco_entry import DiscoEntryType
# from ..text.name import Name
from ..wiki import EntertainmentEntity, DiscographyEntry, Artist, DiscographyEntryPart, TVSeries
from ..wiki.discography import DiscographyMixin, Discography

__all__ = ['show_wiki_entity', 'pprint_wiki_page']
AlbTypes = Optional[set[DiscoEntryType]]


def pprint_wiki_page(url: str, mode: str):
    page = MediaWikiClient.page_for_article(url)
    page.intro(True)
    page.sections.pprint(mode)


def show_wiki_entity(
    identifier: str, expand=0, limit=0, alb_types: Iterable[str] = None, etype: str = None, site: str = None
):
    alb_types = _album_types(alb_types)
    cls = EntertainmentEntity
    if etype:
        for _cls in EntertainmentEntity._subclasses:
            if _cls.__name__ == etype and issubclass(_cls, EntertainmentEntity):    # _subclasses is from WikiEntity
                cls = _cls
                break
        else:
            raise ValueError(f'Invalid EntertainmentEntity subclass: {etype!r}')

    if URL_MATCH(identifier):
        entity = cls.from_url(identifier)
    elif (path := Path(identifier)).exists():
        if not site or cls is EntertainmentEntity:
            raise RuntimeError('A site and entity type is required for entities loaded from files')
        page = WikiPage(path.stem, site, path.read_text('utf-8'), cls._categories, client=MediaWikiClient(site))
        entity = cls.from_page(page)
    else:
        entity = cls.from_title(
            identifier, search=True, research=True, strict=1,
            # name=Name.from_enclosed(identifier)
        )
    uprint(f'{entity}:')

    if isinstance(entity, DiscographyEntry):
        print_disco_entry(entity, 2, expand > 0, limit, expand > 1)
    elif isinstance(entity, Artist):
        print_artist(entity, 2, expand, expand > 2, expand > 3, alb_types)
    elif isinstance(entity, Discography):
        print_discography(
            entity,
            indent=2,
            expand_disco=expand > 0,
            editions=expand > 1,
            track_info=expand > 2,
            alb_types=alb_types,
            header=True,
        )
    elif isinstance(entity, TVSeries):
        print_tv_series(entity, 2)
    else:
        uprint(f'  - No additional information is configured for {entity.__class__.__name__} entities')


def print_tv_series(tv_series: TVSeries, indent: int = 0):
    prefix = ' ' * indent
    if links := tv_series.soundtrack_links():
        uprint(f'{prefix}Discography Links:')
        for link in sorted(links):
            uprint(f'{prefix}  - {link!r}')
    else:
        uprint(f'{prefix}Discography Links: [Unavailable]')


def print_artist(
    artist: Artist,
    indent: int = 0,
    expand_disco: int = 0,
    editions: bool = False,
    track_info: bool = False,
    alb_types: AlbTypes = None,
):
    prefix = ' ' * indent
    uprint(f'{prefix}- {artist.name}:')
    if names := artist.names:
        uprint(f'{prefix}  Names:')
        for name in names:
            # uprint(f'{prefix}    - {name}')
            uprint(f'{prefix}    - {name.full_repr(include_versions=False)}')
            if name.versions:
                for version in name.versions:
                    # uprint(f'{prefix}       - {version}')
                    uprint(f'{prefix}       - {version.full_repr()}')

    if langs := artist.languages:
        primary = artist.language
        uprint(f'{prefix}  Languages:')
        for lang in langs:
            if primary and lang == primary:
                uprint(f'{prefix}    - {lang} (primary)')
            else:
                uprint(f'{prefix}    - {lang}')
    else:
        uprint(f'{prefix}  Languages: (unknown)')

    if expand_disco:
        print_discography(artist, indent, expand_disco > 1, editions, track_info, alb_types)


def print_discography(
    entity: DiscographyMixin,
    indent: int = 0,
    expand_disco: bool = False,
    editions: bool = False,
    track_info: bool = False,
    alb_types: AlbTypes = None,
    header: bool = False,
):
    prefix = ' ' * indent
    if header:
        # noinspection PyUnresolvedReferences
        uprint(f'{prefix}- {entity.name}:')
    if discography := entity.discography:
        uprint(f'{prefix}  Discography:')
        for disco_entry in sorted(discography):
            if not alb_types or disco_entry.type in alb_types:
                if expand_disco:
                    print_disco_entry(disco_entry, indent + 6, editions, track_info=track_info)
                else:
                    uprint(f'{prefix}    - {disco_entry}')
                    # uprint(f'{prefix}    - {disco_entry}: {list(disco_entry.pages)}')
    else:
        uprint(f'{prefix}  Discography: [Unavailable]')


def print_disco_entry(
    disco_entry: DiscographyEntry,
    indent: int = 0,
    editions: bool = False,
    limit: int = 0,
    track_info: bool = False,
):
    prefix = ' ' * indent
    suffix = '' if disco_entry.editions else f' [{"Edition" if editions else "Part"} info unavailable]'
    uprint(f'{prefix}- {disco_entry}:{suffix}')
    if names := disco_entry.names:
        uprint(f'{prefix}  Names:')
        for name in names:
            # uprint(f'{prefix}    - {name}')
            uprint(f'{prefix}    - {name.full_repr(include_versions=False)}')

    counter = count(1)
    if editions:
        for edition in disco_entry:
            uprint(f'{prefix}  - {edition}:')
            uprint(f'{prefix}      Artist: {edition.artist}')
            if edition:
                uprint(f'{prefix}      Parts:')
                for part in edition:
                    print_de_part(part, indent + 8, track_info)
                    if limit and next(counter) == limit:
                        break
            else:
                uprint(f'{prefix}      Parts: [Unavailable]')
    else:
        uprint(f'{prefix}  Parts:')
        for part in disco_entry.parts():
            print_de_part(part, indent + 4, track_info)
            if limit and next(counter) == limit:
                break


def print_de_part(part: DiscographyEntryPart, indent: int = 0, track_info: bool = False):
    prefix = ' ' * indent
    if part:
        uprint(f'{prefix}- {part}:')
        if part.artists:
            uprint(f'{prefix}    Artists:')
            for artist in sorted(part.artists):
                uprint(f'{prefix}      - {artist}')

        uprint(f'{prefix}    Tracks:')
        for track in part:
            uprint(f'{prefix}      - {track._repr()}')
            if track_info:
                uprint(f'{prefix}          Full name: {track.full_name()!r}')
                uprint(f'{prefix}          Name: {track.name.full_repr()}')
    else:
        uprint(f'{prefix}- {part}: [Track info unavailable]')


def _album_types(alb_types: Optional[Iterable[str]]) -> AlbTypes:
    return {DiscoEntryType.for_name(t) for t in alb_types} if alb_types else None
