"""
:author: Doug Skrypa
"""

import json
import logging
import re
from pathlib import Path
from typing import Union, Optional, Dict, Any, Tuple

from ds_tools.compat import cached_property
from ds_tools.core import Paths
from ds_tools.input import choose_item
from ds_tools.output import colored
from ..files import iter_album_dirs, AlbumDir, SafePath, SongFile, get_common_changes
from ..wiki import Track, Artist, Singer, Group
from ..wiki.album import DiscographyEntry, DiscographyEntryPart, Soundtrack, SoundtrackEdition, SoundtrackPart
from ..wiki.parsing.utils import LANG_ABBREV_MAP
from ..wiki.typing import StrOrStrs
from .enums import CollabMode as CM
from .exceptions import MatchException
from .wiki_match import find_album
from .wiki_utils import get_disco_part, DiscoObj

__all__ = ['update_tracks']
log = logging.getLogger(__name__)
CONFIG_DIR = Path('~/.config/music_manager/').expanduser()
ARTIST_TYPE_DIRS = SafePath('{artist}/{type_dir}')
SOLO_DIR_FORMAT = SafePath('{artist}/Solo/{singer}')
TRACK_NAME_FORMAT = SafePath('{num:02d}. {track}.{ext}')
ArtistType = Union[Artist, Group, Singer, 'ArtistSet']
TrackUpdates = Dict[SongFile, Dict[str, Any]]
UpdateCounts = Dict[str, Dict[Tuple[Any, Any], int]]
UPPER_CHAIN_SEARCH = re.compile(r'[A-Z]{2,}').search


def update_tracks(
    paths: Paths, dry_run=False, soloist=False, hide_edition=False, collab_mode: Union[CM, str] = CM.ARTIST,
    url: Optional[str] = None, add_bpm=False, dest_base_dir: Union[Path, str, None] = None, title_case=False,
    sites: StrOrStrs = None, dump: Optional[str] = None, load: Optional[str] = None,
):
    if not isinstance(collab_mode, CM):
        collab_mode = CM(collab_mode)
    if dest_base_dir is not None and not isinstance(dest_base_dir, Path):
        dest_base_dir = Path(dest_base_dir).expanduser().resolve()

    if dump:
        dump = Path(dump).expanduser().resolve()
    if load:
        load = Path(load).expanduser().resolve()

    if url:
        album_dirs = list(iter_album_dirs(paths))
        if len(album_dirs) > 1:
            log.debug(f'Found dirs: {album_dirs}')
            raise ValueError('When a wiki URL is provided, only one album can be processed at a time')

        entry = DiscographyEntry.from_url(url)
        AlbumUpdater(album_dirs[0], entry, dry_run, soloist, hide_edition, collab_mode, title_case).update(
            dest_base_dir, add_bpm, dump, load
        )
    else:
        for album_dir in iter_album_dirs(paths):
            try:
                updater = AlbumUpdater.for_album_dir(
                    album_dir, dry_run, soloist, hide_edition, collab_mode, title_case, sites
                )
            except MatchException as e:
                log.log(e.lvl, e, extra={'color': 9})
                log.debug(e, exc_info=True)
            else:
                updater.update(dest_base_dir, add_bpm, dump, load)


class AlbumUpdater:
    def __init__(
            self, album_dir: AlbumDir, album: DiscoObj, dry_run=False, soloist=False, hide_edition=False,
            collab_mode: CM = CM.ARTIST, title_case=False
    ):
        self.soloist = soloist
        self.hide_edition = hide_edition
        self.collab_mode = collab_mode
        self.dry_run = dry_run
        self.album_dir = album_dir
        self.album = album
        self.title_case = title_case

    @classmethod
    def for_album_dir(
            cls, album_dir: AlbumDir, dry_run=False, soloist=False, hide_edition=False, collab_mode: CM = CM.ARTIST,
            title_case=False, sites: StrOrStrs = None
    ) -> 'AlbumUpdater':
        try:
            album = find_album(album_dir, sites=sites)
        except Exception as e:
            if isinstance(e, ValueError) and e.args[0] == 'No candidates found':
                raise MatchException(30, f'No match found for {album_dir} ({album_dir.name})') from e
            else:
                raise MatchException(40, f'Error finding an album match for {album_dir}: {e}') from e
        else:
            log.info(f'Matched {album_dir} to {album}')
            return cls(album_dir, album, dry_run, soloist, hide_edition, collab_mode, title_case)

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

    def __get_track_updates(self) -> TrackUpdates:
        disk_num = self.disco_part.disc
        alb_name = self._normalize_name(self.disco_part.full_name(self.hide_edition))
        values = {
            'album_artist': self.album_artist_name, 'artist': self.artist_name, 'disk': disk_num,
            'date': self.edition.date.strftime('%Y%m%d'), 'album': alb_name
        }
        if lang := self.edition.lang:
            lang = LANG_ABBREV_MAP.get(lang.lower())
            if lang in ('Chinese', 'Japanese', 'Korean', 'Mandarin'):
                values['genre'] = f'{lang[0]}-pop'

        updates = {}
        for file, track in self.file_track_map.items():
            updates[file] = file_values = values.copy()
            file_values['title'] = self._normalize_name(track.full_name(self.collab_mode in (CM.TITLE, CM.BOTH)))
            if self.ost and (extras := track.name.extra):
                # noinspection PyUnboundLocalVariable
                extras.pop('artists', None)
            track_artist_name = track.artist_name(self.artist_name, self.collab_mode in (CM.ARTIST, CM.BOTH))
            file_values['artist'] = self.artist_name if self.ost else track_artist_name
            if file.tag_type == 'mp4':
                file_values['track'] = (track.num, len(self.file_track_map))        # TODO: Handle incomplete file set
                file_values['disk'] = (disk_num, disk_num)                          # TODO: get actual disk count
            else:
                file_values['track'] = track.num

        return updates

    def _get_track_updates(self, load: Optional[Path] = None) -> TrackUpdates:
        if load:
            log.info(f'Loading track updates from {load}')
            with load.open('r', encoding='utf-8') as f:
                _updates = json.load(f)

            files = {f.path.as_posix(): f for f in self.album_dir.songs}
            return {files[k]: v for k, v in _updates.items()}
        else:
            return self.__get_track_updates()

    def _apply_track_updates(self, dump: Optional[Path] = None, load: Optional[Path] = None):
        updates = self._get_track_updates(load)
        if dump:
            log.info(f'Dumping track updates that would be made to {dump}')
            _updates = {file.path.as_posix(): values for file, values in updates.items()}
            with dump.open('w', encoding='utf-8') as f:
                json.dump(_updates, f, sort_keys=True, indent=4, ensure_ascii=False)
            return False

        include_collabs = self._artist != self.artist
        common_changes = get_common_changes(self.album_dir, updates, extra_newline=True, dry_run=self.dry_run)
        prefix = '[DRY RUN] Would rename' if self.dry_run else 'Renaming'
        for file, values in updates.items():
            track = self.file_track_map[file]
            log.debug(f'Matched {file} to {track.name.full_repr()}')
            file.update_tags(values, self.dry_run, no_log=common_changes)
            track_name = self._normalize_name(track.full_name(include_collabs))
            filename = TRACK_NAME_FORMAT(track=track_name, ext=file.ext, num=track.num)
            if file.path.name != filename:
                rel_path = Path(file.rel_path)
                log.info(f'{prefix} {rel_path.parent}/{colored(rel_path.name, 11)} -> {colored(filename, 10)}')
                if not self.dry_run:
                    file.rename(file.path.with_name(filename))

        return True

    def _move_album_dir(self, dest_base_dir: Optional[Path] = None):
        edition = self.edition
        artist_name = self.artist.name.english
        alb_artist_name = self.album_artist.name.english
        solo_of_group = isinstance(self.artist, Singer) and self.artist.groups and not self.soloist
        rel_dir_fmt = _album_format(
            edition.date, edition.type.numbered and edition.entry.number, solo_of_group and self.ost
        )
        if dest_base_dir is None:
            dest_base_dir = self.album_dir.path.parent
        else:
            if solo_of_group and not self.ost:
                rel_dir_fmt = SOLO_DIR_FORMAT + rel_dir_fmt
            else:
                rel_dir_fmt = ARTIST_TYPE_DIRS + rel_dir_fmt

        expected_rel_dir = rel_dir_fmt(
            artist=alb_artist_name, type_dir=edition.type.directory, album_num=edition.numbered_type,
            album=self.disco_part.full_name(self.hide_edition), date=edition.date.strftime('%Y.%m.%d'),
            singer=artist_name
        )
        expected_dir = dest_base_dir.joinpath(expected_rel_dir)
        if expected_dir != self.album_dir.path:
            prefix = '[DRY RUN] Would move' if self.dry_run else 'Moving'
            log.info(f'{prefix} {self.album_dir} -> {expected_dir}')
            if not self.dry_run:
                orig_parent_path = self.album_dir.path.parent
                self.album_dir.move(expected_dir)
                for path in (orig_parent_path, orig_parent_path.parent):
                    log.log(19, f'Checking directory: {path}')
                    if path.exists() and next(path.iterdir(), None) is None:
                        log.log(19, f'Removing empty directory: {path}')
                        path.rmdir()
        else:
            log.log(19, f'Album {self.album_dir} is already in the expected dir: {expected_dir}')

    def update(
        self,
        dest_base_dir: Optional[Path] = None,
        add_bpm=False,
        dump: Optional[Path] = None,
        load: Optional[Path] = None,
    ):
        self.album_dir.remove_bad_tags(self.dry_run)
        self.album_dir.fix_song_tags(self.dry_run, add_bpm)
        log.info(f'Artist for {self.edition}: {self.artist}')
        if self._apply_track_updates(dump, load):
            self._move_album_dir(dest_base_dir)


class ArtistSet:
    def __init__(self, artists, english):
        self.name = self            # Prevent needing to have a separate class for the fake Name
        self.artists = artists
        self.english = english

    def __str__(self):
        return ', '.join(str(a.name) for a in self.artists)


def _album_format(date, num, solo_ost):
    if date and num:
        return SafePath('[{date}] {album} [{album_num}]')
    elif date:
        return SafePath('[{date}] {album} [{singer} solo]' if solo_ost else '[{date}] {album}')
    elif num:
        return SafePath('{album} [{album_num}]')
    else:
        return SafePath('{album} [{singer} solo]' if solo_ost else '{album}')
