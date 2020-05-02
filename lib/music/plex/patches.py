"""
:author: Doug Skrypa
"""

import atexit
import logging

from plexapi.audio import Track, Album, Artist
from plexapi.base import PlexObject
from plexapi.playlist import Playlist

from ..common.utils import stars

__all__ = ['apply_plex_patches', 'track_repr']
log = logging.getLogger(__name__)


def cls_name(obj):
    return obj.__class__.__name__


def track_repr(self, rating=None):
    fmt = '<{}#{}[{}]({!r}, artist={!r}, album={!r})>'
    rating = stars(rating or self.userRating)
    artist = self.originalTitle if self.grandparentTitle == 'Various Artists' else self.grandparentTitle
    return fmt.format(cls_name(self), self._int_key(), rating, self.title, artist, self.parentTitle)


def apply_plex_patches(deinit_colorama=True):
    """
    Monkey-patch...
      - Playlist to support semi-bulk item removal (the Plex REST API does not have a bulk removal handler, but the
        removeItems method added below removes the reload step between items)
      - Track, Album, and Artist to have more readable/useful reprs
      - PlexObject to be sortable
      - PlexObject to have an as_dict() method

    :param bool deinit_colorama: plexapi.utils imports tqdm (it uses it to print a progress bar during downloads); when
      importing tqdm, tqdm imports and initializes colorama.  Colorama ends up raising exceptions when piping output to
      ``| head``.  Defaults to True.
    """
    if deinit_colorama:
        try:
            import colorama
        except ImportError:
            pass
        else:
            colorama.deinit()
            atexit.unregister(colorama.initialise.reset_all)

    def removeItems(self, items):
        """ Remove multiple tracks from a playlist. """
        del_method = self._server._session.delete
        uri_fmt = '{}/items/{{}}'.format(self.key)
        results = [self._server.query(uri_fmt.format(item.playlistItemID), method=del_method) for item in items]
        self.reload()
        return results

    def album_repr(self):
        fmt = '<{}#{}[{}]({!r}, artist={!r}, genres={})>'
        rating = stars(float(self._data.attrib.get('userRating', 0)))
        genres = ', '.join(g.tag for g in self.genres)
        return fmt.format(cls_name(self), self._int_key(), rating, self.title, self.parentTitle, genres)

    def artist_repr(self):
        fmt = '<{}#{}[{}]({!r}, genres={})>'
        rating = stars(float(self._data.attrib.get('userRating', 0)))
        genres = ', '.join(g.tag for g in self.genres)
        return fmt.format(cls_name(self), self._int_key(), rating, self.title, genres)

    def full_info(ele):
        return {'_type': ele.tag, 'attributes': ele.attrib, 'elements': [full_info(e) for e in ele]}

    PlexObject._int_key = lambda self: int(self._clean(self.key))
    PlexObject.__lt__ = lambda self, other: int(self._clean(self.key)) < int(other._clean(other.key))
    PlexObject.as_dict = lambda self: full_info(self._data)

    Playlist.removeItems = removeItems
    Track.__repr__ = track_repr
    Album.__repr__ = album_repr
    Artist.__repr__ = artist_repr
