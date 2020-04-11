"""
:author: Doug Skrypa
"""

import logging
from collections import defaultdict
from typing import List, Union

from ds_tools.core import Paths
from ds_tools.output import uprint
from ..files import AlbumDir, iter_album_dirs
from ..wiki.artist import Artist, Group
from .exceptions import NoArtistFoundException

__all__ = ['show_matches']
log = logging.getLogger(__name__)


def show_matches(paths: Paths):
    for album_dir in iter_album_dirs(paths):
        uprint(f'- Album: {album_dir}')
        try:
            artists = find_artists(album_dir)
        except NoArtistFoundException:
            log.error(f'    - Artist: No artist could be found', extra={'color': 11})
        except Exception as e:
            log.error(f'    - Artist: {e}', extra={'color': 'red'}, exc_info=True)
        else:
            if len(artists) == 1:
                artist = artists[0]
                try:
                    uprint(f'    - Artist: {artist} / {artist.name}')
                except Exception:
                    log.error(f'    - Artist: Error parsing name:', extra={'color': 'red'}, exc_info=True)
            else:
                uprint(f'    - Artists ({len(artists)}):')
                for artist in artists:
                    uprint(f'        - {artist}')

            # if errors:
            #     uprint(f'    - Artist Errors ({len(errors)}):')
            #     for error_list in errors.values():
            #         for error in error_list:
            #             err_str = '\n          '.join(str(error).splitlines())
            #             log.error(f'        - {err_str}', extra={'color': 'red'})


def find_artists(album_dir: AlbumDir) -> List[Artist]:
    if artists := album_dir.artists:
        log.debug(f'Processing {artists=}', extra={'color': 14})
        remaining = set(artists)
        artist_objs = []

        groups = defaultdict(set)
        for artist in artists:
            if extra := artist.extra:
                if (group := extra.get('group')) and group.english:
                    groups[group.english].add(artist)

        if group_names := set(groups):
            log.debug(f'Retrieving {group_names=}', extra={'color': 14})
            group_obj_dict = Group.from_titles(group_names, search=True)

            for title, group_obj in group_obj_dict.items():
                log.debug(f'Found {group_obj=}', extra={'color': 10})
                for name in groups[title]:
                    log.debug(f'Looking for a singer that matches {name=!r}', extra={'color': 2})
                    for singer in group_obj.members:
                        log.debug(f'Comparing {singer=} to {name=}')
                        if singer.name.matches(name):
                            log.debug(f'Found {singer=!r} == {name=!r}', extra={'color': 10})
                            artist_objs.append(singer)
                            remaining.discard(name)
                            break
                    else:
                        log.warning(f'No match found for {name.artist_str()}', extra={'color': 11})

        if remaining:
            log.debug(f'Retrieving {remaining=}', extra={'color': 14})
            if artist_names := {a.english for a in artists if a.english and a.english != 'Various Artists'}:
                artist_obj_dict = Artist.from_titles(artist_names, search=True)
                for title, artist_obj in artist_obj_dict.items():
                    artist_objs.append(artist_obj)

        return artist_objs

    raise NoArtistFoundException(album_dir)
