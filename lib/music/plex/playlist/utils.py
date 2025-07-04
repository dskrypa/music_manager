from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict, NotRequired

if TYPE_CHECKING:
    from ..server import LocalPlexServer

    OptServer = LocalPlexServer | None

__all__ = ['PlaylistXmlDict', 'get_plex']


def get_plex(plex: OptServer = None) -> LocalPlexServer:
    """Workaround for the circular dependency"""
    if plex is None:
        from ..server import LocalPlexServer

        plex = LocalPlexServer()

    return plex


class PlaylistXmlDict(TypedDict):
    name: NotRequired[str]
    playlist: str
    tracks: list[str]
