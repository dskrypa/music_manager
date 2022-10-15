"""
:author: Doug Skrypa
"""

from typing import TYPE_CHECKING, Iterable, Union, TypeVar, Type, Mapping

from wiki_nodes import WikiPage, Link

if TYPE_CHECKING:
    from .base import WikiEntity  # noqa
    from .disco_entry import DiscoEntry  # noqa

__all__ = ['WE', 'Pages', 'PageEntry', 'StrOrStrs', 'Candidates']

WE = TypeVar('WE', bound='WikiEntity')
Pages = Union[dict[str, WikiPage], Iterable[WikiPage], None]
PageEntry = Union[WikiPage, 'DiscoEntry']
StrOrStrs = Union[str, Iterable[str], None]
Candidates = Mapping[Link, tuple[Type[WE], PageEntry]]
