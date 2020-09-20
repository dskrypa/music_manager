"""
:author: Doug Skrypa
"""

import logging
from typing import List, Iterable, Optional, Set

from ds_tools.fs.paths import Paths
from ds_tools.input import choose_item
from ds_tools.output import uprint
from ds_tools.unicode import LangCat
from wiki_nodes.http import URL_MATCH
from ..common.disco_entry import DiscoEntryType
from ..files import AlbumDir, iter_album_dirs
from ..text.name import Name
from ..wiki.album import DiscographyEntryPart, DiscographyEntry, Soundtrack
from ..wiki.artist import Artist, Group
from ..wiki.exceptions import AmbiguousPagesError, AmbiguousPageError
from ..wiki.typing import StrOrStrs
from .exceptions import NoArtistFoundException
from .wiki_info import print_de_part

__all__ = ['show_matches', 'find_artists', 'find_album', 'test_match']
log = logging.getLogger(__name__)
mlog = logging.getLogger(f'{__name__}.matching')
mlog.setLevel(logging.WARNING)


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


def show_matches(paths: Paths, sites: StrOrStrs = None):
    for album_dir in iter_album_dirs(paths):
        uprint(f'- Album: {album_dir}')
        try:
            artists = find_artists(album_dir, sites=sites)
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


def find_artists(album_dir: AlbumDir, sites: StrOrStrs = None) -> List[Artist]:
    # TODO: Look at TXXX:WIKI:ARTIST tag
    if artists := album_dir.all_artists:
        log.debug(f'Processing artists in {album_dir}: {artists}')
        remaining = set(artists)
        artist_objs = []
        if groups := album_dir._groups:
            wiki_groups = Group.from_titles(set(groups), search=True, strict=1, research=True, sites=sites)
            for title, group_obj in wiki_groups.items():
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
                try:
                    _artists = Artist.from_titles(artist_names, search=True, strict=1, research=True, sites=sites)
                except (AmbiguousPageError, AmbiguousPagesError) as e:
                    if all(a.english == a.english.upper() for a in artist_names):
                        log.debug(e)
                        artist_names = {a.with_part(_english=a.english.title()) for a in artist_names}
                        _artists = Artist.from_titles(artist_names, search=True, strict=1, research=True, sites=sites)
                    else:
                        raise

                for name, artist in _artists.items():
                    artist_objs.append(artist)
                    remaining.discard(name)

        for name in remaining:
            artist_objs.append(Artist(name.artist_str()))

        return artist_objs

    raise NoArtistFoundException(album_dir)


def find_album(
    album_dir: AlbumDir,
    artists: Optional[Iterable[Artist]] = None,
    sites: StrOrStrs = None,
) -> DiscographyEntryPart:
    # TODO: Look at TXXX:WIKI:URL tag
    album_name = album_dir.name
    if not album_name:
        raise ValueError(f'Directories with multiple album names are not currently handled.')
    repackage = album_name.repackage
    alb_name = album_name.name

    artists = artists or find_artists(album_dir, sites=sites)
    log.debug(f'Processing album for {album_dir} with {album_name=!r} ({repackage=}) and {artists=}')
    candidates = _find_album(album_dir, alb_name, artists, album_dir.type, repackage, album_name.number)
    if not candidates and alb_name.eng_lang == LangCat.MIX and alb_name.eng_langs.intersection(LangCat.non_eng_cats):
        split = alb_name.split()
        log.log(19, f'Re-attempting album match with name={split.full_repr()}')
        candidates = _find_album(album_dir, split, artists, album_dir.type, repackage, album_name.number)

    return choose_item(
        candidates, 'candidate', before=f'\nFound multiple possible matches for {album_name}', before_color=14
    )


def _find_album(
        album_dir: AlbumDir, alb_name: Name, artists: Iterable[Artist], alb_type: Optional[DiscoEntryType], repackage,
        num
) -> Set[DiscographyEntryPart]:
    track_count = len(album_dir)
    candidates = set()
    for artist in artists:
        for entry in artist.all_discography_entries_editions:
            if not alb_type or alb_type.compatible_with(entry.type):
                if alb_name and alb_name.matches(entry.name):
                    entry_parts = list(entry.parts() if isinstance(entry, DiscographyEntry) else entry)
                    pkg_match_parts = [p for p in entry_parts if p.repackage == repackage]
                    # mlog.debug(f'{entry=} has {len(entry_parts)} parts; {len(pkg_match_parts)} match {repackage=!r}')
                    if pkg_match_parts:
                        mlog.debug(
                            f'{entry=} has {len(entry_parts)} parts; {len(pkg_match_parts)} match {repackage=!r}',
                            extra={'color': 11}
                        )
                        for part in pkg_match_parts:
                            if track_count == len(part) \
                                    or any(pt.name.matches(at.tag_title) for pt, at in zip(part, album_dir)):
                                mlog.debug(f'{part=} matches {alb_name}', extra={'color': 11})
                                candidates.add(part)
                    else:
                        if entry_parts:
                            pkg_repr = ', '.join(f'{part}.repackage={part.repackage!r}' for part in entry_parts)
                            mlog.debug(f'Found no matching parts for {entry=}: {pkg_repr}', extra={'color': 8})
                        else:
                            mlog.debug(f'Found no parts for {entry=}', extra={'color': 8})
                elif alb_type and alb_type == entry.type and num and entry.number and num == entry.number:
                    if parts := list(entry.parts() if isinstance(entry, DiscographyEntry) else entry):
                        mlog.debug(f'{entry=} has {len(parts)} parts that match by type + number', extra={'color': 11})
                        candidates.update(parts)
                else:
                    mlog.debug(f'{alb_name!r} does not match {entry}', extra={'color': 8})

    if not candidates and alb_type == DiscoEntryType.Soundtrack:
        if name_str := alb_name.english or alb_name.non_eng:
            try:
                candidates.add(Soundtrack.from_name(name_str))
            except Exception as e:
                log.debug(f'Error finding soundtrack for {name_str=!r}: {e}')

    if len(candidates) > 1:
        candidates = _filter_candidates(album_dir, candidates)
    return candidates


def _filter_candidates(album_dir: AlbumDir, candidates: Set[DiscographyEntryPart]) -> Set[DiscographyEntryPart]:
    mlog.debug('Initial candidates ({}):\n{}'.format(len(candidates), '\n'.join(f' - {c}' for c in candidates)))

    track_count = len(album_dir)
    _candidates, candidates = candidates, set()
    for part in _candidates:
        if track_count == len(part):
            candidates.add(part)
    if not candidates:
        mlog.debug(f'No candidates had matching track counts')
        candidates = _candidates

    _candidates, candidates = candidates, set()
    for part in _candidates:
        track_match_pct = sum(1 for pt, at in zip(part, album_dir) if pt.name.matches(at.tag_title)) / track_count
        mlog.debug(f'{part=} tracks with names matching {album_dir}: {track_match_pct:.2%}')
        if track_match_pct > 0.7:
            candidates.add(part)

    if not candidates:
        mlog.debug(f'No candidates had matching track names')
        candidates = _candidates

    return candidates
