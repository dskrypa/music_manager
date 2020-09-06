"""
:author: Doug Skrypa
"""

import json
import logging
import re
from functools import cached_property
from pathlib import Path
from typing import Union, Optional, Dict, Tuple, Iterator

from ds_tools.core import Paths
from ds_tools.input import choose_item
from ..files import iter_album_dirs, AlbumDir, SongFile
from ..wiki import Track, Artist, Singer, Group
from ..wiki.album import DiscographyEntry, DiscographyEntryPart, Soundtrack, SoundtrackEdition, SoundtrackPart
from ..wiki.parsing.utils import LANG_ABBREV_MAP
from ..wiki.typing import StrOrStrs
from .enums import CollabMode
from .exceptions import MatchException
from .update import AlbumInfo, TrackInfo
from .wiki_match import find_album
from .wiki_utils import get_disco_part, DiscoObj

__all__ = ['update_tracks']
log = logging.getLogger(__name__)
ArtistType = Union[Artist, Group, Singer, 'ArtistSet']

CONFIG_DIR = Path('~/.config/music_manager/').expanduser()
UPPER_CHAIN_SEARCH = re.compile(r'[A-Z]{2,}').search


def update_tracks(
    paths: Paths,
    dry_run=False,
    soloist=False,
    hide_edition=False,
    collab_mode: Union[CollabMode, str] = CollabMode.ARTIST,
    url: Optional[str] = None,
    add_bpm=False,
    dest_base_dir: Union[Path, str, None] = None,
    title_case=False,
    sites: StrOrStrs = None,
    dump: Optional[str] = None,
    load: Optional[str] = None,
    artist_url=None,
):
    collab_mode = CollabMode.get(collab_mode)
    if dest_base_dir is not None and not isinstance(dest_base_dir, Path):
        dest_base_dir = Path(dest_base_dir).expanduser().resolve()

    for album_dir, album_info in iter_album_info(
        paths, soloist, hide_edition, collab_mode, url, title_case, sites, load, artist_url
    ):
        album_dir.remove_bad_tags(dry_run)
        album_dir.fix_song_tags(dry_run, add_bpm)
        if dump:
            album_info.dump(Path(dump).expanduser().resolve())
            return
        else:
            album_info.update_and_move(album_dir, dest_base_dir, dry_run)


def iter_album_info(
    paths: Paths,
    soloist: bool = False,
    hide_edition: bool = False,
    collab_mode: CollabMode = CollabMode.ARTIST,
    url: Optional[str] = None,
    title_case: bool = False,
    sites: StrOrStrs = None,
    load: Optional[str] = None,
    artist_url: Optional[str] = None,
) -> Iterator[Tuple[AlbumDir, AlbumInfo]]:
    if load:
        album_info = AlbumInfo.load(Path(load).expanduser().resolve())
        yield album_info.album_dir, album_info
    else:
        artist = Artist.from_url(artist_url) if artist_url is not None else None
        if url:
            album_dirs = list(iter_album_dirs(paths))
            if len(album_dirs) > 1:
                log.debug(f'Found dirs: {album_dirs}')
                raise ValueError('When a wiki URL is provided, only one album can be processed at a time')

            album_dir = album_dirs[0]
            entry = DiscographyEntry.from_url(url)
            processor = AlbumInfoProcessor(album_dir, entry, artist, soloist, hide_edition, collab_mode, title_case)
            yield album_dir, processor.to_album_info()
        else:
            for album_dir in iter_album_dirs(paths):
                try:
                    processor = AlbumInfoProcessor.for_album_dir(
                        album_dir, artist, soloist, hide_edition, collab_mode, title_case, sites
                    )
                except MatchException as e:
                    log.log(e.lvl, e, extra={'color': 9})
                    log.debug(e, exc_info=True)
                else:
                    yield album_dir, processor.to_album_info()


class AlbumInfoProcessor:
    def __init__(
        self,
        album_dir: AlbumDir,
        album: DiscoObj,
        artist: Optional[Artist] = None,
        soloist: bool = False,
        hide_edition: bool = False,
        collab_mode: CollabMode = CollabMode.ARTIST,
        title_case: bool = False,
    ):
        self.album_dir = album_dir
        self.title_case = title_case
        self.soloist = soloist
        self.hide_edition = hide_edition
        self.collab_mode = collab_mode
        self.album = album
        self.__artist = artist

    @classmethod
    def for_album_dir(
        cls,
        album_dir: AlbumDir,
        artist: Optional[Artist] = None,
        soloist: bool = False,
        hide_edition: bool = False,
        collab_mode: CollabMode = CollabMode.ARTIST,
        title_case: bool = False,
        sites: StrOrStrs = None,
    ) -> 'AlbumInfoProcessor':
        try:
            album = find_album(album_dir, sites=sites)
        except Exception as e:
            if isinstance(e, ValueError) and e.args[0] == 'No candidates found':
                raise MatchException(30, f'No match found for {album_dir} ({album_dir.name})') from e
            else:
                raise MatchException(40, f'Error finding an album match for {album_dir}: {e}') from e
        else:
            log.info(f'Matched {album_dir} to {album}')
            return cls(album_dir, album, artist, soloist, hide_edition, collab_mode, title_case)

    def to_album_info(self) -> AlbumInfo:
        log.info(f'Artist for {self.edition}: {self.artist}')
        if (ed_lang := self.edition.lang) and (lang := LANG_ABBREV_MAP.get(ed_lang.lower())):
            # noinspection PyUnboundLocalVariable
            genre = f'{lang[0]}-pop' if lang in ('Chinese', 'Japanese', 'Korean', 'Mandarin') else None
        else:
            genre = None

        mp4 = all(file.tag_type == 'mp4' for file in self.album_dir)
        album_info = AlbumInfo(
            title=self._normalize_name(self.disco_part.full_name(self.hide_edition)),
            artist=self.album_artist_name,
            date=self.edition.date,
            disk=(self.disco_part.disc, self.disco_part.disc) if mp4 else self.disco_part.disc,
            genre=genre,
            name=self.disco_part.full_name(self.hide_edition),
            parent=self.album_artist.name.english,
            singer=self.artist.name.english,
            solo_of_group=isinstance(self.artist, Singer) and self.artist.groups and not self.soloist,
            type=self.edition.type,
            number=self.edition.entry.number,
            numbered_type=self.edition.numbered_type,
        )

        include_collabs = self._artist != self.artist
        total_tracks = len(self.file_track_map)
        for file, track in self.file_track_map.items():
            log.debug(f'Matched {file} to {track.name.full_repr()}')
            title = self._normalize_name(track.full_name(self.collab_mode in (CollabMode.TITLE, CollabMode.BOTH)))
            if self.ost and (extras := track.name.extra):
                # noinspection PyUnboundLocalVariable
                extras.pop('artists', None)
            track_artist_name = track.artist_name(
                self.artist_name, self.collab_mode in (CollabMode.ARTIST, CollabMode.BOTH)
            )
            album_info.tracks[file.path.as_posix()] = TrackInfo(
                album_info,
                title=title,
                artist=self.artist_name if self.ost else track_artist_name,
                num=(track.num, total_tracks) if mp4 else track.num,
                name=self._normalize_name(track.full_name(include_collabs)),
            )

        return album_info

    @cached_property
    def disco_part(self) -> Union[DiscographyEntryPart, SoundtrackPart]:
        if isinstance(self.album, Soundtrack):
            self.hide_edition = True
            full, parts = self.album.split_editions()
            full_len = len(full.parts[0]) if full and full.parts else None
            entry = full if full_len and len(self.album_dir) == full_len else parts
        else:
            entry = self.album
        if isinstance(entry, SoundtrackEdition):
            if len(entry.parts) == 1:
                entry = entry.parts[0]
            elif alb_part := self.album_dir.name.part:
                for part in entry.parts:
                    # noinspection PyUnresolvedReferences
                    if part.part == alb_part:
                        entry = part
                        break
        return get_disco_part(entry)

    @cached_property
    def edition(self):
        return self.disco_part.edition

    @cached_property
    def ost(self):
        return isinstance(self.disco_part, SoundtrackPart)

    @cached_property
    def file_track_map(self) -> Dict[SongFile, Track]:
        ft_iter = zip(sorted(self.album_dir.songs, key=lambda sf: sf.track_num), self.disco_part.tracks)
        return {file: track for file, track in ft_iter}

    @cached_property
    def artist_name_overrides(self) -> Dict[str, str]:
        overrides_path = CONFIG_DIR.joinpath('artist_name_overrides.json')
        if overrides_path.exists():
            log.debug(f'Loading {overrides_path}')
            with overrides_path.open('r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def normalize_artist(self, artist) -> str:
        artist_name = str(artist)
        if override := self.artist_name_overrides.get(artist_name):
            log.debug(f'Overriding {artist_name=!r} with {override!r}')
            return override
        return artist_name

    @cached_property
    def _artists(self):
        if isinstance(self.disco_part, SoundtrackPart):
            return sorted(self.disco_part.artists)
        return sorted(self.edition.artists)

    @cached_property
    def _artist(self) -> ArtistType:
        artists = self._artists
        if len(artists) > 1:
            others = set(artists)
            artist = choose_item(artists + ['[combine all]'], 'artist', self.disco_part)
            if artist == '[combine all]':
                path_artist = choose_item(
                    artists + ['Various Artists'], 'artist', before_color=13,
                    before='\nWhich artist\'s name should be used in the file path?'
                )
                if path_artist != 'Various Artists':
                    path_artist = path_artist.name.english
                artist = ArtistSet(artists, path_artist)
            else:
                others.remove(artist)
                for track in self.file_track_map.values():
                    track.add_collabs(others)
        else:
            artist = artists[0]

        return artist

    @cached_property
    def artist(self) -> ArtistType:
        if self.__artist is not None:
            return self.__artist
        artist = self._artist
        # noinspection PyUnresolvedReferences
        if self.ost and not self.edition.full_ost:
            if name := artist.name.english or artist.name.non_eng:
                try:
                    return Artist.from_title(name, sites=['kpop.fandom.com', 'www.generasia.com'])
                except Exception as e:
                    log.warning(f'Error finding alternate version of {artist=!r}: {e}')
        return artist

    @cached_property
    def _artist_group(self) -> Optional[Group]:
        artist = self.artist
        if isinstance(artist, Singer) and artist.groups and not self.soloist:
            return choose_item(artist.groups, 'group', before=f'Found multiple groups for {artist}')
        return None

    @cached_property
    def album_artist(self) -> ArtistType:
        return self._artist_group or self.artist

    @cached_property
    def album_artist_name(self) -> str:
        if group := self._artist_group:
            return f'{self.normalize_artist(self.artist.name)} ({group.name})'
        return self.normalize_artist(self.album_artist.name)

    @cached_property
    def artist_name(self) -> str:
        artist_name = self.normalize_artist(self.artist.name)
        if group := self._artist_group:
            return f'{artist_name} ({group.name})'
        return artist_name

    def _normalize_name(self, name: str) -> str:
        if self.title_case and UPPER_CHAIN_SEARCH(name) or name.lower() == name:
            name = name.title().replace("I'M ", "I'm ")
        return name


class ArtistSet:
    def __init__(self, artists, english):
        self.name = self            # Prevent needing to have a separate class for the fake Name
        self.artists = artists
        self.english = english

    def __str__(self):
        return ', '.join(str(a.name) for a in self.artists)
