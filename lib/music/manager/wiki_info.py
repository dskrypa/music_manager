"""
:author: Doug Skrypa
"""

from itertools import count
from typing import Optional, Iterable, Set

from ds_tools.output import uprint
from wiki_nodes.http import URL_MATCH, MediaWikiClient
from ..common import DiscoEntryType
from ..text import Name
from ..wiki import EntertainmentEntity, DiscographyEntry, Artist, DiscographyEntryPart
from ..wiki.discography import DiscographyMixin, Discography

__all__ = ['show_wiki_entity', 'pprint_wiki_page']
AlbTypes = Optional[Set[DiscoEntryType]]


def pprint_wiki_page(url: str, mode: str):
    page = MediaWikiClient.page_for_article(url)
    page.intro(True)
    page.sections.pprint(mode)


def show_wiki_entity(
        identifier: str, expand=0, limit=0, alb_types: Optional[Iterable[str]] = None, etype: Optional[str] = None
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
        print_discography(entity, 2, expand > 0, expand > 1, expand > 2, alb_types, True)
    else:
        uprint(f'  - No additional information is configured for {entity.__class__.__name__} entities')


def print_artist(
        artist: Artist, indent=0, expand_disco=0, editions=False, track_info=False, alb_types: AlbTypes = None
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
        entity: DiscographyMixin, indent=0, expand_disco=False, editions=False, track_info=False,
        alb_types: AlbTypes = None, header=False
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


def print_disco_entry(disco_entry: DiscographyEntry, indent=0, editions=False, limit=0, track_info=False):
    prefix = ' ' * indent
    suffix = '' if disco_entry.editions else ' [{} info unavailable]'.format('Edition' if editions else 'Part')
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


def print_de_part(part: DiscographyEntryPart, indent=0, track_info=False):
    prefix = ' ' * indent
    if part:
        uprint(f'{prefix}- {part}:')
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
