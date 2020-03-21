"""
:author: Doug Skrypa
"""

from itertools import count

from ds_tools.output import uprint
from ..wiki import WikiEntity, DiscographyEntry, Artist, DiscographyEntryPart

__all__ = ['show_wiki_entity']


def show_wiki_entity(url, expand=0, limit=0):
    entity = WikiEntity.from_url(url)
    uprint(f'{entity}:')

    if isinstance(entity, DiscographyEntry):
        print_disco_entry(entity, 2, expand > 0, limit)
    elif isinstance(entity, Artist):
        print_artist(entity, 2, expand > 0, expand > 1)
    else:
        uprint(f'  - No additional information is configured for {entity.__class__.__name__} entities')


def print_artist(artist: Artist, indent=0, expand_disco=False, editions=False):
    prefix = ' ' * indent
    uprint(f'{prefix}- {artist.name}:')
    discography = artist.discography
    if discography:
        uprint(f'{prefix}  Discography:')
        for disco_entry in sorted(discography):
            if expand_disco:
                print_disco_entry(disco_entry, indent + 6, editions)
            else:
                uprint(f'{prefix}    - {disco_entry}')
    else:
        uprint(f'{prefix}  Discography: [Unavailable]')


def print_disco_entry(disco_entry: DiscographyEntry, indent=0, editions=False, limit=0):
    prefix = ' ' * indent
    suffix = '' if disco_entry.editions else ' [{} info unavailable]'.format('Edition' if editions else 'Part')
    uprint(f'{prefix}- {disco_entry}:{suffix}')
    counter = count(1)
    if editions:
        for edition in disco_entry.editions:
            uprint(f'{prefix}  - {edition}:')
            uprint(f'{prefix}      Artist: {edition.artist}')
            if edition.parts:
                uprint(f'{prefix}      Parts:')
                for part in edition:
                    print_de_part(part, indent + 8)
                    if limit and next(counter) == limit:
                        break
            else:
                uprint(f'{prefix}      Parts: [Unavailable]')
    else:
        for part in disco_entry:
            print_de_part(part, indent + 4)
            if limit and next(counter) == limit:
                break


def print_de_part(part: DiscographyEntryPart, indent=0):
    prefix = ' ' * indent
    if part.tracks:
        uprint(f'{prefix}- {part}:')
        uprint(f'{prefix}    Tracks:')
        for track in part:
            uprint(f'{prefix}      - {track._repr()}')
    else:
        uprint(f'{prefix}- {part}: [Track info unavailable]')
