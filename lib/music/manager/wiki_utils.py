"""
:author: Doug Skrypa
"""

import logging
from typing import Union

from ds_tools.input import choose_item
from ..wiki import DiscographyEntry, DiscographyEntryEdition, DiscographyEntryPart

__all__ = ['get_disco_part', 'DiscoObj']
log = logging.getLogger(__name__)
DiscoObj = Union[DiscographyEntry, DiscographyEntryEdition, DiscographyEntryPart]


def get_disco_part(entry: DiscoObj) -> DiscographyEntryPart:
    if isinstance(entry, DiscographyEntry):
        entry = choose_item(entry.editions, 'edition', entry)
    if isinstance(entry, DiscographyEntryEdition):
        entry = choose_item(entry.parts, 'part', entry)
    if isinstance(entry, DiscographyEntryPart):
        return entry
    else:
        raise TypeError(f'Expected a DiscographyEntryPart, but {entry=} is a {type(entry).__name__}')
