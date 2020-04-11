"""
:author: Doug Skrypa
"""

import logging
from typing import TYPE_CHECKING, Iterable, Union, Dict, TypeVar, Type, Tuple, Mapping

from wiki_nodes import WikiPage, Link

if TYPE_CHECKING:
    from .base import WikiEntity
    from .disco_entry import DiscoEntry

__all__ = ['WE', 'Pages', 'PageEntry', 'StrOrStrs']
log = logging.getLogger(__name__)

WE = TypeVar('WE', bound='WikiEntity')
Pages = Union[Dict[str, WikiPage], Iterable[WikiPage], None]
PageEntry = Union[WikiPage, 'DiscoEntry']
StrOrStrs = Union[str, Iterable[str], None]
Candidates = Mapping[Link, Tuple[Type[WE], PageEntry]]
