"""
:author: Doug Skrypa
"""

from itertools import count

from ds_tools.output import uprint
from wiki_nodes.http import URL_MATCH
from ..wiki import WikiEntity, DiscographyEntry, Artist, DiscographyEntryPart

__all__ = ['show_wiki_entity']


def show_wiki_entity(identifier: str, expand=0, limit=0):
    if URL_MATCH(identifier):
        entity = WikiEntity.from_url(identifier)
    else:
        entity = WikiEntity.from_title(identifier, search=True)
    uprint(f'{entity}:')

    if isinstance(entity, DiscographyEntry):
        print_disco_entry(entity, 2, expand > 0, limit, expand > 1)
    elif isinstance(entity, Artist):
        print_artist(entity, 2, expand > 0, expand > 1, expand > 2)
    else:
        uprint(f'  - No additional information is configured for {entity.__class__.__name__} entities')


def print_artist(artist: Artist, indent=0, expand_disco=False, editions=False, track_info=False):
    prefix = ' ' * indent
    uprint(f'{prefix}- {artist.name}:')
    discography = artist.discography
    if discography:
        uprint(f'{prefix}  Discography:')
        for disco_entry in sorted(discography):
            if expand_disco:
                print_disco_entry(disco_entry, indent + 6, editions, track_info=track_info)
            else:
                uprint(f'{prefix}    - {disco_entry}')
    else:
        uprint(f'{prefix}  Discography: [Unavailable]')


def print_disco_entry(disco_entry: DiscographyEntry, indent=0, editions=False, limit=0, track_info=False):
    prefix = ' ' * indent
    suffix = '' if disco_entry.editions else ' [{} info unavailable]'.format('Edition' if editions else 'Part')
    uprint(f'{prefix}- {disco_entry}:{suffix}')
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
    else:
        uprint(f'{prefix}- {part}: [Track info unavailable]')
