"""

"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from music.files.exceptions import TagNotFound

if TYPE_CHECKING:
    from music.files.track.track import SongFile

__all__ = ['get_raw_cover_image']
log = logging.getLogger(__name__)


def get_raw_cover_image(track: SongFile, propagate_not_found: bool = False) -> Optional[bytes]:
    try:
        return track.get_cover_data()[0]
    except TagNotFound as e:
        log.warning(e)
        if propagate_not_found:
            raise
        return None
    except Exception:  # noqa
        log.error(f'Unable to load cover image for {track}', exc_info=True)
        return None
