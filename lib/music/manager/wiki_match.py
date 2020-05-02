"""
:author: Doug Skrypa
"""

import logging
from typing import List, Iterable, Optional

from ds_tools.core import Paths
from ds_tools.input import choose_item
from ds_tools.output import uprint
from wiki_nodes.http import URL_MATCH
from ..files import AlbumDir, iter_album_dirs
from ..wiki.album import DiscographyEntryPart, DiscographyEntry
from ..wiki.artist import Artist, Group
from .exceptions import NoArtistFoundException
from .wiki_info import print_de_part

__all__ = ['show_matches', 'find_artists', 'find_album', 'test_match']
log = logging.getLogger(__name__)


def test_match(paths: Paths, identifier: str):
    for album_dir in iter_album_dirs(paths):
        album_name = album_dir.name
        if not album_name:
            raise ValueError(f'Directories with multiple album names are not currently handled.')

        if URL_MATCH(identifier):
            disco_entry = DiscographyEntry.from_url(identifier)
        else:
            disco_entry = DiscographyEntry.from_title(identifier, search=True, research=True)

        uprint(f'Match scores for {album_name!r}:')
        de_score = album_name.name._score(disco_entry.name)
        uprint(f'  - {disco_entry}: {de_score}')
        for edition in disco_entry:
            ed_score = album_name.name._score(edition.name)
            uprint(f'    - {edition}: {ed_score}')
            for part in edition:
                p_score = album_name.name._score(part.name)
                uprint(f'      - {part}: {p_score}')


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
                    uprint(f'    - Artist: {artist} / {artist.names}')
                except Exception:
                    log.error(f'    - Artist: Error parsing name:', extra={'color': 'red'}, exc_info=True)
            else:
                uprint(f'    - Artists ({len(artists)}):')
                for artist in artists:
                    uprint(f'        - {artist} / {artist.names}')

            try:
                album = find_album(album_dir, artists)
            except Exception as e:
                log.error(f'    - Album: {e}', extra={'color': 'red'}, exc_info=True)
            else:
                print_de_part(album, 4)


def find_artists(album_dir: AlbumDir) -> List[Artist]:
    if artists := album_dir.all_artists:
        log.debug(f'Processing artists in {album_dir}: {artists}')
        remaining = set(artists)
        artist_objs = []
        if groups := album_dir._groups:
            for title, group_obj in Group.from_titles(set(groups), search=True, strict=1, research=True).items():
                log.debug(f'Found {group_obj=}', extra={'color': 10})
                for name in groups[title]:
                    if singer := group_obj.find_member(name):
                        artist_objs.append(singer)
                        remaining.discard(name)
                    else:
                        log.warning(f'No match found for {name.artist_str()}', extra={'color': 11})

        if remaining:
            log.debug(f'Processing remaining artists in {album_dir}: {remaining}', extra={'color': 14})
            if artist_names := {a for a in artists if a.english != 'Various Artists'}:
                for name, artist in Artist.from_titles(artist_names, search=True, strict=1, research=True).items():
                    artist_objs.append(artist)
                    remaining.discard(name)

        for name in remaining:
            artist_objs.append(Artist(name.artist_str()))

        return artist_objs

    raise NoArtistFoundException(album_dir)


def find_album(album_dir: AlbumDir, artists: Optional[Iterable[Artist]] = None) -> DiscographyEntryPart:
    album_type = album_dir.type
    album_name = album_dir.name
    if not album_name:
        raise ValueError(f'Directories with multiple album names are not currently handled.')

    before = f'Found multiple possible matches for {album_name}'
    candidates = []
    artists = artists or find_artists(album_dir)
    log.debug(f'Processing album for {album_dir} with {album_name=!r} and {artists=}')
    for artist in artists:
        for disco_entry in artist.all_discography_entries:
            if not album_type or album_type == disco_entry.type:
                if album_name.name.matches(disco_entry.name):
                    if parts := list(disco_entry.parts()):
                        candidates.extend(parts)
                        # if len(parts) == 1:
                        #     candidates.append(parts[0])
                        # else:
                        #     part = choose_item(parts, 'part', before=before)
                        #     candidates.append(part)
                #     else:
                #         log.debug(f'Found no parts for {disco_entry=}')
                # else:
                #     log.debug(f'{album_name} does not match {disco_entry} ({disco_entry._pages})')

    return choose_item(candidates, 'candidate', before=before)
