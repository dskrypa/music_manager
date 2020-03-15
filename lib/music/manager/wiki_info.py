"""
:author: Doug Skrypa
"""

import logging

from ..wiki import WikiEntity, DiscographyEntry, Artist

__all__ = ['show_wiki_entity']
log = logging.getLogger(__name__)


def show_wiki_entity(url):
    entity = WikiEntity.from_url(url)
    log.info(f'{entity}:')

    if isinstance(entity, DiscographyEntry):
        for edition in entity.editions:
            log.info(f'  - {edition}:')
            log.info(f'    Artist: {edition.artist}')
            log.info(f'    Parts:')
            for part in edition:
                log.info(f'      - {part}:')
                log.info(f'        Tracks:')
                for track in part:
                    log.info(f'          - {track}')
    elif isinstance(entity, Artist):
        log.info(f'  - Name: {entity.name}')
        discography = entity.discography
        if discography:
            log.info(f'    Discography:')
            for disco_entry in sorted(discography):
                log.info(f'      - {disco_entry}')
        else:
            log.info(f'    Discography: [Unavailable]')
    else:
        log.info(f'  - No additional information is configured for {entity.__class__.__name__} entities')
