"""
:author: Doug Skrypa
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Union, Iterable, Iterator, Collection

from ds_tools.output.terminal import uprint
from ds_tools.unicode import LangCat
from wiki_nodes.http.utils import URL_MATCH

from ..common.prompts import choose_item
from ..files.album import AlbumDir, iter_album_dirs
from ..text.name import Name
from ..wiki.album import DiscographyEntryPart, DiscographyEntry, Soundtrack, Album, DEEntryOrEdition, DEPart
from ..wiki.artist import Artist, Group
from ..wiki.exceptions import AmbiguousWikiPageError
from ..wiki.typing import StrOrStrs
from .exceptions import NoArtistMatchFoundException
from .wiki_info import print_de_part

if TYPE_CHECKING:
    from ds_tools.fs.typing import Paths
    from ..files.parsing import AlbumName

__all__ = ['show_matches', 'find_artists', 'AlbumFinder', 'test_match']
log = logging.getLogger(__name__)
mlog = logging.getLogger(f'{__name__}.matching')
mlog.setLevel(logging.WARNING)

DEPartOrEntry = Union[DiscographyEntryPart, DiscographyEntry]


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
        except NoArtistMatchFoundException:
            log.error(f'    - Artist: No artist could be found', extra={'color': 11})
        except Exception as e:
            log.error(f'    - Artist: {e}', extra={'color': 'red'}, exc_info=True)
        else:
            if len(artists) == 1:
                artist = artists[0]
                try:
                    uprint(f'    - Artist: {artist} / {artist.names}')
                except Exception:  # noqa
                    log.error(f'    - Artist: Error parsing name:', extra={'color': 'red'}, exc_info=True)
            else:
                uprint(f'    - Artists ({len(artists)}):')
                for artist in artists:
                    uprint(f'        - {artist} / {artist.names}')

            try:
                album = AlbumFinder(album_dir, artists, sites).find_album()
            except Exception as e:
                log.error(f'    - Album: {e}', extra={'color': 'red'}, exc_info=True)
            else:
                print_de_part(album, 4)


def find_artists(album_dir: AlbumDir, sites: StrOrStrs = None) -> list[Artist]:
    if artist_url := album_dir.artist_url:
        log.debug(f'Found artist URL via tag for {album_dir}: {artist_url}', extra={'color': 10})
        return [Artist.from_url(artist_url)]
    elif artists := album_dir.all_artists:
        log.debug(f'Processing artists in {album_dir}: {artists}')
        sites = sites or _sites_for(album_dir)
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
                except AmbiguousWikiPageError as e:
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

    raise NoArtistMatchFoundException(album_dir)


class AlbumFinder:
    __slots__ = ('album_dir', 'artists', 'sites')
    album_dir: AlbumDir
    artists: Iterable[Artist]
    sites: StrOrStrs

    def __init__(self, album_dir: AlbumDir, artists: Iterable[Artist] = None, sites: StrOrStrs = None):
        self.album_dir = album_dir
        self.artists = artists
        self.sites = sites

    def find_album(self) -> DiscographyEntryPart:
        album_dir = self.album_dir
        if album_url := album_dir.album_url:
            return self._from_album_dir_url(album_url)
        elif album_name := album_dir.name:
            return self._from_album_name(album_name)
        elif album_dir.names == {None}:
            if len(album_dir) == 1 and (album_name := album_dir.songs[0].title_as_album_name):
                log.debug(f'Using single {album_name=}')
                return self._from_album_name(album_name)
            raise ValueError(f'No album name is defined for album={album_dir.path.as_posix()!r}')
        else:
            raise ValueError('Directories with multiple album names are not currently handled.')

    def _choose_candidate(self, candidates, name=None) -> DEPartOrEntry:
        before = f'\nFound multiple possible matches for {name or self.album_dir}'
        return choose_item(candidates, 'candidate', before=before, before_color=14)

    def _from_album_dir_url(self, album_url: str) -> DEPartOrEntry:
        log.debug(f'Found album URL via tag for {self.album_dir}: {album_url}', extra={'color': 10})
        candidates = list(DiscographyEntry.from_url(album_url).parts())
        if len(candidates) > 1:
            _candidates = candidates.copy()
            candidates = _filter_candidates(self.album_dir, candidates) or _candidates

        return self._choose_candidate(candidates)

    def _from_album_name(self, album_name: AlbumName) -> DEPartOrEntry:
        album_dir = self.album_dir
        name: Name = album_name.name
        artists = self.artists or find_artists(album_dir, sites=self.sites)
        log.debug(
            f'Processing album for {album_dir} with {album_name=} (repackage={album_name.repackage}) and {artists=}',
            extra={'color': (0, 14)}
        )

        if candidates := self._find_candidates(name, artists, album_name):
            return self._choose_candidate(candidates, album_name)
        elif name.eng_lang == LangCat.MIX and name.eng_langs.intersection(LangCat.non_eng_cats):
            split = name.split()
            log.log(19, f'Re-attempting album match with name={split.full_repr()}', extra={'color': (0, 11)})
            candidates = self._find_candidates(split, artists, album_name)

        return self._choose_candidate(candidates, album_name)

    def _find_candidates(self, name: Name, artists: Iterable[Artist], album_name: AlbumName) -> set[DEPartOrEntry]:
        if candidates := self._get_artist_candidates(name, artists, album_name):
            return _filter_candidates(self.album_dir, candidates) if len(candidates) > 1 else candidates
        elif not (name_str := name.english or name.non_eng):
            return candidates

        cls = Soundtrack if album_name.ost else Album
        log.debug(f'No candidates found - attempting {cls.__name__} search for {name_str=}', extra={'color': (0, 13)})
        try:
            candidates.add(cls.from_name(name_str))
        except Exception:  # noqa
            log.debug(f'Error finding {cls.__name__} for {name_str=!r}:', exc_info=True, extra={'color': (0, 9)})

        return _filter_candidates(self.album_dir, candidates) if len(candidates) > 1 else candidates

    def _get_artist_candidates(self, name: Name, artists: Iterable[Artist], album_name: AlbumName) -> set[DEPartOrEntry]:
        alb_type = self.album_dir.type
        repackage, num = album_name.repackage, album_name.number
        track_count = len(self.album_dir)

        candidates = set()
        for artist in artists:
            for entry in artist.all_discography_entries_editions:
                if not alb_type or alb_type.compatible_with(entry.type):
                    candidates.update(self._artist_candidates(name, repackage, num, track_count, entry))

        return candidates

    def _artist_candidates(
        self, name: Name, repackage: bool, num: int, track_count: int, entry: DEEntryOrEdition
    ) -> Iterator[DEPartOrEntry]:
        alb_dir = self.album_dir
        alb_type = alb_dir.type
        if name and name.matches(entry.name):
            entry_parts = tuple(entry.parts() if isinstance(entry, DiscographyEntry) else entry)
            pkg_match_parts = [p for p in entry_parts if p.repackage == repackage]
            # mlog.debug(f'{entry=} has {len(entry_parts)} parts; {len(pkg_match_parts)} match {repackage=!r}')
            if pkg_match_parts:
                mlog.debug(
                    f'{entry=} has {len(entry_parts)} parts; {len(pkg_match_parts)} match {repackage=!r}',
                    extra={'color': 11}
                )
                for part in pkg_match_parts:
                    if self._tracks_match(part, track_count):
                        mlog.debug(f'{part=} matches {name}', extra={'color': 11})
                        yield part
            else:
                if entry_parts:
                    pkg_repr = ', '.join(f'{part}.repackage={part.repackage!r}' for part in entry_parts)
                    mlog.debug(f'Found no matching parts for {entry=}: {pkg_repr}', extra={'color': 8})
                else:
                    mlog.debug(f'Found no parts for {entry=}', extra={'color': 8})
        elif alb_type and alb_type == entry.type and num and entry.number and num == entry.number:
            if parts := tuple(entry.parts() if isinstance(entry, DiscographyEntry) else entry):
                mlog.debug(f'{entry=} has {len(parts)} parts that match by type + number', extra={'color': 11})
                yield from parts
        else:
            mlog.debug(f'{name!r} does not match {entry._basic_repr}', extra={'color': 8})

    def _tracks_match(self, part: DEPart, track_count: int) -> bool:
        # mlog.debug(f'Comparing {track_count=} with {part=}')
        if track_count == len(part):
            return True
        # mlog.debug(f'Comparing track names with {part=}')
        return any(part_track.name.matches(alb_track.tag_title) for part_track, alb_track in zip(part, self.album_dir))


def _filter_candidates(album_dir: AlbumDir, candidates: Collection[DiscographyEntryPart]) -> set[DiscographyEntryPart]:
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

    album_name = album_dir.name
    if album_name.ost:
        candidates = _filter_ost_parts(album_dir.name, candidates)

    return candidates


def _filter_ost_parts(album_name: AlbumName, candidates):
    _candidates = set(c for c in candidates if getattr(c, 'part', None) == album_name.part)
    return _candidates if _candidates else candidates


def _sites_for(album_dir: AlbumDir) -> tuple[str, ...]:
    if album_dir.name.ost:
        return ('kpop.fandom.com', 'www.generasia.com', 'wiki.d-addicts.com')
        # return ('kpop.fandom.com', 'wiki.d-addicts.com')
    return ('kpop.fandom.com', 'www.generasia.com')
    # return ('kpop.fandom.com',)
