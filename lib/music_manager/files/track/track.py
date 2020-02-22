"""
:author: Doug Skrypa
"""

import logging
import re
from pathlib import Path

from ds_tools.compat import cached_property
from .base import BaseSongFile

__all__ = ['SongFile']
log = logging.getLogger(__name__)


class SongFile(BaseSongFile):
    @classmethod
    def for_plex_track(cls, track, root):
        return cls(Path(root).joinpath(track.media[0].parts[0].file).resolve())

    @cached_property
    def album_from_dir(self):
        album = self.path.parent.name
        if album.lower().startswith(self.tag_artist.lower()):
            album = album[len(self.tag_artist):].strip()
        if album.startswith('- '):
            album = album[1:].strip()
        m = re.match(r'^\[\d{4}[0-9.]*\] (.*)$', album)     # Begins with date
        if m:
            album = m.group(1).strip()
        m = re.match(r'(.*)\s*\[.*Album\]', album)          # Ends with Xth Album
        if m:
            album = m.group(1).strip()
        return album

    @cached_property
    def in_competition_album(self):
        try:
            album_artist = self.tag_text('album_artist')
        except Exception:
            return False
        else:
            if album_artist.lower().startswith('produce'):
                if album_artist.split()[-1].isdigit():
                    return True
        return False

    @cached_property
    def _is_full_ost(self):
        album_artist = self.tag_text('album_artist', default='').lower()
        album_name = self.album_name_cleaned
        full_ost = album_name.endswith('OST') and 'part' not in album_name.lower()
        alb_dir = self.album_dir_obj
        multiple_artists = len({f.tag_artist for f in alb_dir}) > 1
        return full_ost and album_artist == 'various artists' and multiple_artists and len(alb_dir) > 2

    @cached_property
    def album_name_cleaner(self):
        album = self.album_name_cleaned
        m = re.match(r'(.*)(\((?:vol.?|volume) (?:\d+|[ivx]+)\))$', album, re.IGNORECASE)
        if m:
            album = m.group(1)
        return album

    @cached_property
    def _artist_path(self):
        bad = (
            'album', 'single', 'soundtrack', 'collaboration', 'solo', 'christmas', 'download', 'compilation',
            'unknown_fixme', 'mixtape'
        )
        artist_path = self.path.parents[1]
        lc_name = artist_path.name.lower()
        if not any(i in lc_name for i in bad):
            return artist_path

        artist_path = artist_path.parent
        lc_name = artist_path.name.lower()
        if not any(i in lc_name for i in bad):
            return artist_path
        log.debug('Unable to determine artist path for {}'.format(self))
        return None

    @cached_property
    def album_type_dir(self):
        return self.path.parents[1].name
