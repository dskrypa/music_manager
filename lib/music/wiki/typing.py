"""
:author: Doug Skrypa
"""

from datetime import date
from typing import TYPE_CHECKING, Iterable, Union, Optional, TypeVar, Type, Mapping, MutableMapping

from wiki_nodes import WikiPage, Link

if TYPE_CHECKING:
    from .base import WikiEntity  # noqa
    from .disco_entry import DiscoEntry  # noqa

__all__ = ['WE', 'Pages', 'PageEntry', 'Candidates', 'StrOrStrs', 'OptStr', 'StrDateMap']

WE = TypeVar('WE', bound='WikiEntity')

Pages = Union[dict[str, WikiPage], Iterable[WikiPage], None]
PageEntry = Union[WikiPage, 'DiscoEntry']
Candidates = Mapping[Link, tuple[Type[WE], PageEntry]]

StrOrStrs = Union[str, Iterable[str], None]
OptStr = Optional[str]
StrDateMap = MutableMapping[OptStr, date]
