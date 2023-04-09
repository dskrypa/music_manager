"""
:author: Doug Skrypa
"""

from ..common.prompts import choose_item
from ..wiki.album import DiscoObj, DiscographyEntry, DiscographyEntryEdition, DiscographyEntryPart

__all__ = ['get_disco_part']


def get_disco_part(entry: DiscoObj) -> DiscographyEntryPart:
    # TODO: Include link to URL in the prompt
    if isinstance(entry, DiscographyEntry):
        entry = choose_item(entry.editions, 'edition', entry)
    if isinstance(entry, DiscographyEntryEdition):
        entry = choose_item(entry.parts, 'part', entry)
    if isinstance(entry, DiscographyEntryPart):
        return entry
    else:
        raise TypeError(f'Expected a DiscographyEntryPart, but {entry=} is a {type(entry).__name__}')
