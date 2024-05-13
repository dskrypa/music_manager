"""
:author: Doug Skrypa
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Union, Iterable, Iterator, Collection

from ds_tools.output.terminal import uprint
from ds_tools.unicode import LangCat
from wiki_nodes.http.utils import URL_MATCH

from music.common.disco_entry import DiscoEntryType
from ..common.prompts import choose_item
from ..files.album import AlbumDir, iter_album_dirs
from ..files.parsing import AlbumName, split_artists
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

__all__ = ['show_album_dir_matches', 'AlbumFinder', 'test_match', 'AlbumMetaData', 'AlbumDirMetaData']
log = logging.getLogger(__name__)
mlog = logging.getLogger(f'{__name__}.matching')
mlog.setLevel(logging.WARNING)

DEPartOrEntry = Union[DiscographyEntryPart, DiscographyEntry]
GroupedNames = dict[str, set[Name]]


def test_match(paths: Paths, identifier: str):
    for album_dir in iter_album_dirs(paths):
        if not (album_name := album_dir.name):
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


def show_album_dir_matches(paths: Paths, sites: StrOrStrs = None):
    for album_dir in iter_album_dirs(paths):
        uprint(f'- Album: {album_dir}')
        show_matches(AlbumDirMetaData(album_dir), sites)


def show_matches(album_meta: AlbumMetaData, sites: StrOrStrs = None):
    try:
        artists = ArtistFinder.for_meta(album_meta, sites).find_meta_artists(album_meta)
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
            album = AlbumFinder(album_meta, artists, sites).find_album()
        except Exception as e:
            log.error(f'    - Album: {e}', extra={'color': 'red'}, exc_info=True)
        else:
            print_de_part(album, 4)


class ArtistFinder:
    __slots__ = ('sites',)

    def __init__(self, sites: StrOrStrs = None):
        self.sites = sites

    @classmethod
    def for_dir(cls, album_dir: AlbumDir, sites: StrOrStrs = None) -> ArtistFinder:
        return cls.for_meta(AlbumDirMetaData(album_dir), sites)

    @classmethod
    def for_meta(cls, album_meta: AlbumMetaData, sites: StrOrStrs = None) -> ArtistFinder:
        return cls(sites or _sites_for(album_meta))

    def find_dir_artists(self, album_dir: AlbumDir) -> list[Artist]:
        return self.find_meta_artists(AlbumDirMetaData(album_dir))

    def find_meta_artists(self, album_meta: AlbumMetaData) -> list[Artist]:
        if artist_url := album_meta.artist_url:
            log.debug(f'Found artist URL via tag for {album_meta}: {artist_url}', extra={'color': 10})
            return [Artist.from_url(artist_url)]
        elif artists := album_meta.all_artists:
            log.debug(f'Processing artists in {album_meta}: {artists}')
            return self.find_names(artists, album_meta.groups)
        else:
            raise NoArtistMatchFoundException(album_meta)

    def find_name(self, name: str) -> list[Artist]:
        return self.find_names(split_artists(name))

    def find_names(self, names: Collection[Name], groups: GroupedNames | None = None) -> list[Artist]:
        if groups:
            artist_objs, remaining = self._process_groups(names, groups)
        else:
            artist_objs, remaining = [], set(names)

        if not remaining:
            return artist_objs

        log.debug(f'Processing remaining artists: {remaining}', extra={'color': 14})
        if artist_names := {a for a in names if a.english != 'Various Artists'}:
            for name, artist in self._get_artists(artist_names).items():
                artist_objs.append(artist)
                remaining.discard(name)

        if remaining:
            artist_objs.extend(Artist(name.artist_str()) for name in remaining)

        return artist_objs

    def _process_groups(self, artists: Collection[Name], groups: GroupedNames) -> tuple[list[Artist], set[Name]]:
        remaining = set(artists)
        artist_objs = []
        wiki_groups = Group.from_titles(set(groups), search=True, strict=1, research=True, sites=self.sites)
        for title, group_obj in wiki_groups.items():
            log.debug(f'Found {group_obj=}', extra={'color': 10})
            for name in groups[title]:
                if singer := group_obj.find_member(name):
                    artist_objs.append(singer)
                    remaining.discard(name)
                else:
                    log.warning(f'No match found for {name.artist_str()}', extra={'color': 11})

        return artist_objs, remaining

    def _get_artists(self, artist_names: Collection[Name]) -> dict[Name, Artist]:
        try:
            return Artist.from_titles(artist_names, search=True, strict=1, research=True, sites=self.sites)
        except AmbiguousWikiPageError as e:
            if all(a.english == a.english.upper() for a in artist_names):
                log.debug(e)
                artist_names = {a.with_part(_english=a.english.title()) for a in artist_names}
                return Artist.from_titles(artist_names, search=True, strict=1, research=True, sites=self.sites)
            else:
                raise


@dataclass
class AlbumMetaData:
    name: AlbumName | None = None
    ## type: DiscoEntryType = DiscoEntryType.UNKNOWN

    artist: Name | None = None
    all_artists: set[Name] = None
    groups: GroupedNames = None

    album_dir: AlbumDir | None = None
    track_count: int = None

    album_url: str | None = None
    artist_url: str | None = None

    @classmethod
    def parse(cls, name: str, artist: str, **kwargs) -> AlbumMetaData:
        album_name = AlbumName.parse(name, artist)
        artists = set(split_artists(artist))
        if album_name.feat:
            artists.update(album_name.feat)
        if len(artists) == 1:
            kwargs['artist'] = next(iter(artists))
        return cls(name=album_name, all_artists=artists, **kwargs)

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__}[name={self.name!r}, artist={self.artist!r}]>'

    @property
    def type(self) -> DiscoEntryType:
        return self.name.type if self.name else DiscoEntryType.UNKNOWN


class DirProperty:
    __slots__ = ('attr',)

    def __init__(self, attr: str = None):
        self.attr = attr

    def __set_name__(self, owner, name):
        if not self.attr:
            self.attr = name

    def __get__(self, instance: AlbumDirMetaData, owner):
        if instance is None:
            return self
        return getattr(instance.album_dir, self.attr)


class AlbumDirMetaData(AlbumMetaData):
    name = DirProperty()
    # type = DirProperty()
    artist = DirProperty()
    all_artists = DirProperty()
    groups = DirProperty('_groups')
    album_url = DirProperty()
    artist_url = DirProperty()

    def __init__(self, album_dir: AlbumDir):
        self.album_dir: AlbumDir = album_dir

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__}({self.album_dir})>'

    @property
    def track_count(self) -> int:
        return len(self.album_dir)


class AlbumFinder:
    __slots__ = ('album_meta', 'artists', 'sites')
    album_meta: AlbumMetaData
    artists: Iterable[Artist]
    sites: StrOrStrs

    def __init__(self, album: AlbumMetaData | AlbumDir, artists: Iterable[Artist] = None, sites: StrOrStrs = None):
        self.album_meta = AlbumDirMetaData(album) if isinstance(album, AlbumDir) else album
        self.artists = artists
        self.sites = sites

    def find_album(self) -> DiscographyEntryPart:
        album_meta = self.album_meta
        if album_url := album_meta.album_url:
            return self._from_album_dir_url(album_url)
        elif album_name := album_meta.name:
            return self._from_album_name(album_name)
        # elif (album_dir := album_meta.album_dir) is None:
        #     raise ValueError('An album name is required to find an album match without an album directory')
        # elif album_dir.names == {None}:
        #     if len(album_dir) == 1 and (album_name := album_dir.songs[0].title_as_album_name):
        #         log.debug(f'Using single {album_name=}')
        #         return self._from_album_name(album_name)
        #     raise ValueError(f'No album name is defined for album={album_dir.path.as_posix()!r}')
        else:
            raise ValueError('Directories with multiple album names are not currently handled.')

    def _choose_candidate(self, candidates, name=None) -> DEPartOrEntry:
        before = f'\nFound multiple possible matches for {name or self.album_meta}'
        # TODO: Include current track count + the count for each candidate in the popup
        return choose_item(candidates, 'candidate', before=before, before_color=14)

    def _from_album_dir_url(self, album_url: str) -> DEPartOrEntry:
        log.debug(f'Found album URL via tag for {self.album_meta}: {album_url}', extra={'color': 10})
        candidates = list(DiscographyEntry.from_url(album_url).parts())
        if len(candidates) > 1:
            _candidates = candidates.copy()
            candidates = _filter_candidates(self.album_meta, candidates) or _candidates

        return self._choose_candidate(candidates)

    def _from_album_name(self, album_name: AlbumName) -> DEPartOrEntry:
        album_meta = self.album_meta
        name: Name = album_name.name
        artists = self.artists or ArtistFinder.for_meta(album_meta, self.sites).find_meta_artists(album_meta)
        log.debug(
            f'Processing album for {album_meta} with {album_name=} (repackage={album_name.repackage}) and {artists=}',
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
            return _filter_candidates(self.album_meta, candidates) if len(candidates) > 1 else candidates
        elif not (name_str := name.english or name.non_eng):
            return candidates

        cls = Soundtrack if album_name.ost else Album
        log.debug(f'No candidates found - attempting {cls.__name__} search for {name_str=}', extra={'color': (0, 13)})
        try:
            candidates.add(cls.from_name(name_str))
        except Exception:  # noqa
            log.debug(f'Error finding {cls.__name__} for {name_str=}:', exc_info=True, extra={'color': (0, 9)})

        return _filter_candidates(self.album_meta, candidates) if len(candidates) > 1 else candidates

    def _get_artist_candidates(
        self, name: Name, artists: Iterable[Artist], album_name: AlbumName
    ) -> set[DEPartOrEntry]:
        alb_type = self.album_meta.type
        repackage, num = album_name.repackage, album_name.number
        candidates = set()
        for artist in artists:
            for entry in artist.all_discography_entries_editions:
                if not alb_type or alb_type.compatible_with(entry.type):
                    candidates.update(self._artist_candidates(name, repackage, num, entry))

        return candidates

    def _artist_candidates(
        self, name: Name, repackage: bool, num: int, entry: DEEntryOrEdition
    ) -> Iterator[DEPartOrEntry]:
        if name and name.matches(entry.name):
            yield from self._name_match_artist_candidates(name, repackage, entry)
        elif (at := self.album_meta.type) and at == entry.type and num and entry.number and num == entry.number:
            if parts := tuple(entry.parts() if isinstance(entry, DiscographyEntry) else entry):
                mlog.debug(f'{entry=} has {len(parts)} parts that match by type + number', extra={'color': 11})
                yield from parts
        else:
            mlog.debug(f'{name!r} does not match {entry._basic_repr}', extra={'color': 8})

    def _name_match_artist_candidates(self, name: Name, repackage: bool, entry: DEEntryOrEdition):
        entry_parts = tuple(entry.parts() if isinstance(entry, DiscographyEntry) else entry)
        pkg_match_parts = [p for p in entry_parts if p.repackage == repackage]
        # mlog.debug(f'{entry=} has {len(entry_parts)} parts; {len(pkg_match_parts)} match {repackage=}')
        if pkg_match_parts:
            mlog.debug(
                f'{entry=} has {len(entry_parts)} parts; {len(pkg_match_parts)} match {repackage=}',
                extra={'color': 11}
            )
            for part in pkg_match_parts:
                if self._tracks_match(part):
                    mlog.debug(f'{part=} matches {name}', extra={'color': 11})
                    yield part
        elif entry_parts:
            pkg_repr = ', '.join(f'{part}.repackage={part.repackage!r}' for part in entry_parts)
            mlog.debug(f'Found no matching parts for {entry=}: {pkg_repr}', extra={'color': 8})
        else:
            mlog.debug(f'Found no parts for {entry=}', extra={'color': 8})

    def _tracks_match(self, part: DEPart) -> bool:
        # mlog.debug(f'Comparing {track_count=} with {part=}')
        if (track_count := self.album_meta.track_count) is None or track_count == len(part):
            # Assume a match when initialized without an album dir
            return True
        # mlog.debug(f'Comparing track names with {part=}')
        try:
            album_dir = self.album_meta.album_dir  # noqa
        except AttributeError:
            return False
        else:
            return any(part_track.name.matches(alb_track.tag_title) for part_track, alb_track in zip(part, album_dir))


def _filter_candidates(
    album_meta: AlbumMetaData, candidates: Collection[DiscographyEntryPart]
) -> set[DiscographyEntryPart]:
    mlog.debug(f'Initial candidates ({len(candidates)}):\n' + '\n'.join(f' - {c}' for c in candidates))

    if (track_count := album_meta.track_count) is not None:
        _candidates = candidates
        if not (candidates := {part for part in _candidates if track_count == len(part)}):
            mlog.debug(f'No candidates had matching track counts')
            candidates = _candidates

    if album_dir := album_meta.album_dir:
        _candidates, candidates = candidates, set()
        for part in _candidates:
            track_match_pct = sum(1 for pt, at in zip(part, album_dir) if pt.name.matches(at.tag_title)) / track_count
            mlog.debug(f'{part=} tracks with names matching {album_dir}: {track_match_pct:.2%}')
            if track_match_pct > 0.7:
                candidates.add(part)

        if not candidates:
            mlog.debug(f'No candidates had matching track names')
            candidates = _candidates

    if album_meta.name.ost:
        candidates = _filter_ost_parts(album_meta.name, candidates)

    return candidates


def _filter_ost_parts(album_name: AlbumName, candidates):
    if filtered := set(c for c in candidates if getattr(c, 'part', None) == album_name.part):
        return filtered
    return candidates


def _sites_for(album_meta: AlbumMetaData) -> tuple[str, ...]:
    if album_meta.name.ost:
        return ('kpop.fandom.com', 'www.generasia.com', 'wiki.d-addicts.com')
        # return ('kpop.fandom.com', 'wiki.d-addicts.com')
    return ('kpop.fandom.com', 'www.generasia.com')
    # return ('kpop.fandom.com',)
