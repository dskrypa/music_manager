"""

"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from tk_gui.images.icons import Icons

from music.files.exceptions import TagNotFound

if TYPE_CHECKING:
    from PIL.Image import Image as PILImage
    from tk_gui.typing import XY
    from music.files.track.track import SongFile

__all__ = ['icon_cache']
log = logging.getLogger(__name__)


class IconCache:
    __slots__ = ('_cache',)

    def __init__(self):
        self._cache = {}

    def get_placeholder(self, size: int) -> PILImage:
        try:
            return self._cache[size]
        except KeyError:
            self._cache[size] = image = Icons(size).draw_alpha_cropped('x')
            return image

    def image_or_placeholder(self, image: Optional[bytes], size: XY | float | int) -> bytes | PILImage:
        if image:
            return image
        try:
            size = int(max(size))
        except TypeError:  # int/float is not iterable
            size = int(size)
        return self.get_placeholder(size)


icon_cache = IconCache()


def get_raw_cover_image(track: SongFile, propagate_not_found: bool = False) -> Optional[bytes]:
    # TODO:
    """
      File "...\git\music_manager\lib\music\files\track\track.py", line 1078, in get_cover_tag
        return self._f.pictures[0]
               ^^^^^^^^^^^^^^^^
    AttributeError: 'OggOpus' object has no attribute 'pictures'
    """
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
